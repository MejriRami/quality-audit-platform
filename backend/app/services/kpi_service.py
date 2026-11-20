"""
kpi_service.py
--------------
All KPI query logic lives here.  The router is a thin shim that calls
these functions and returns their result directly.

Design rules
~~~~~~~~~~~~
* Every public function accepts an explicit `db: Session` as its last
  positional argument and returns a plain dict (JSON-serialisable).
* SQL parameters are always bound – never interpolated – to prevent
  SQL-injection.  The only string that is interpolated is
  `date_trunc_unit`, which is validated to one of {'week','month'}
  before use.
* All helpers are private (leading underscore).
* Reference / grade lines are defined as module-level constants so
  they can be changed in one place.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session
from app.services.scoring_service import (
    VDA_PROCESS,
    resolve_scoring_profile,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AUDIT_HOURS_REFERENCE_LINES = [
    {"value": 140, "label": "Min"},
    {"value": 180, "label": "Max"},
]

AVG_DAYS_CLOSE_CAR_REFERENCE_LINES = [
    {"value": 30, "label": "Target"},
]

WORKING_DAYS_REFERENCE_LINES = [
    {"value": 30, "label": "Target"},
]

STANDARD_AUDIT_GRADE_LINES = [
    {"value": 80, "label": "A"},
    {"value": 60, "label": "B"},
    {"value": 50, "label": "C"},
]

VDA_AUDIT_GRADE_LINES = [
    {"value": 90, "label": "A"},
    {"value": 80, "label": "B"},
]

STANDARD_AUDIT_GRADE_LEGEND = [
    "A: 80 to 100",
    "B: 60 to 79",
    "C: 50 to 59",
    "D: below 50",
]

VDA_AUDIT_GRADE_LEGEND = [
    "A: 90 to 100",
    "B: 80 to 89",
    "C: below 80",
    "SC: special downgrade can still apply when critical VDA rules are triggered",
]

_VALID_INTERVALS = frozenset({"week", "month"})
_VALID_DATE_BASIS = frozenset({"planned", "actual"})
# data_source splits the dashboard: "app" = audits run in this app, "monday" =
# the frozen history imported from Monday. Imported audits are the ones with
# no questionnaire; their CARs follow their audit.
_FOCUS_TYPE_ORDER = ["vda", "plantManagerIATF", "isoIatf", "usageOfGlasses"]
_CLOSED_CAR_STATUSES = ("accepted", "closed")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _validate_interval(interval: str) -> str:
    if interval not in _VALID_INTERVALS:
        raise ValueError(f"interval must be one of {_VALID_INTERVALS}")
    return interval


def _validate_date_basis(date_basis: str) -> str:
    if date_basis not in _VALID_DATE_BASIS:
        raise ValueError(f"date_basis must be one of {_VALID_DATE_BASIS}")
    return date_basis


def _date_trunc_expr(unit: str) -> str:
    """Return the to_char format string for a given truncation unit."""
    if unit == "week":
        return "IYYY-\"W\"IW"
    return "YYYY-MM"


def _pivot_stacked(
    rows: list[tuple[str, str, float]],
    *,
    unit: str,
    group_by: str,
    stack_by: str,
) -> dict[str, Any]:
    """
    Pivot a flat (group, stack, value) result set into the stacked-bar
    format expected by the frontend.

    Returns
    -------
    {
        "groupBy":  str,
        "stackBy":  str,
        "unit":     str,
        "keys":     [str, ...],          # sorted unique stack values
        "data":     [{"group": str, <stack>: float, ...}, ...],
    }
    """
    groups: dict[str, dict[str, Any]] = {}
    keys: set[str] = set()

    def _norm_if_plant(val: str, role: str) -> str:
        if role != "plant":
            return val
        return (val or "").strip().lower()

    for grp, stack, value in rows:
        grp = _norm_if_plant(grp, group_by)
        stack = _norm_if_plant(stack, stack_by)
        keys.add(stack)
        row = groups.setdefault(grp, {"group": grp})
        row[stack] = round(float(row.get(stack, 0.0)) + float(value), 4)

    sorted_keys = sorted(keys)
    data = sorted(groups.values(), key=lambda x: x["group"])

    # Fill missing stacks with 0 so every row has every key
    for d in data:
        for k in sorted_keys:
            d.setdefault(k, 0)

    return {
        "groupBy": group_by,
        "stackBy": stack_by,
        "unit": unit,
        "keys": sorted_keys,
        "data": data,
    }


def _simple_series(
    rows: list[tuple[str, float]],
    *,
    unit: str,
    group_by: str,
) -> dict[str, Any]:
    def _norm_group(val: str) -> str:
        if group_by != "plant":
            return val
        return (val or "").strip().lower()

    return {
        "groupBy": group_by,
        "unit": unit,
        "data": [
            {"group": _norm_group(r[0]), "value": round(float(r[1]), 4)}
            for r in rows
        ],
    }


def _category_series(
    rows: list[tuple[str, float]],
    *,
    unit: str,
    group_by: str,
) -> dict[str, Any]:
    """Same shape as simple_series – kept separate for semantic clarity."""
    return _simple_series(rows, unit=unit, group_by=group_by)


def _safe_pct(part: float, whole: float) -> float:
    if whole <= 0:
        return 0.0
    return round((part / whole) * 100.0, 2)


def _is_closed_sql(expr: str = "ca.status::text") -> str:
    return f"{expr} IN ('{_CLOSED_CAR_STATUSES[0]}', '{_CLOSED_CAR_STATUSES[1]}')"


def _is_open_sql(expr: str = "ca.status::text") -> str:
    return f"(ca.status IS NULL OR {expr} NOT IN ('{_CLOSED_CAR_STATUSES[0]}', '{_CLOSED_CAR_STATUSES[1]}'))"


def _grade_meta_for_profile(profile_key: str | None) -> dict[str, Any]:
    if profile_key == VDA_PROCESS:
        return {
            "gradeLines": VDA_AUDIT_GRADE_LINES,
            "gradeLegend": VDA_AUDIT_GRADE_LEGEND,
            "scoringProfile": "VDA 6.3",
        }
    return {
        "gradeLines": STANDARD_AUDIT_GRADE_LINES,
        "gradeLegend": STANDARD_AUDIT_GRADE_LEGEND,
        "scoringProfile": "Standard",
    }


def _resolve_score_profile_meta(
    db: Session,
    *,
    from_: date | None,
    to: date | None,
    plant: str | None,
    data_source: str = "app",
    audit_type_id: int | None = None,
    date_basis: str,
) -> dict[str, Any]:
    _validate_date_basis(date_basis)

    sql = """
    WITH base AS (
      SELECT DISTINCT
        q.score_calculation::text AS score_calculation,
        q.name::text AS questionnaire_name,
        at.value::text AS audit_type_value,
        f.code::text AS framework_code,
        f.label::text AS framework_label
      FROM audits a
      LEFT JOIN questionnaires q ON q.id = a.questionnaire_id
      LEFT JOIN audit_types at ON at.id = q.type_id
      LEFT JOIN frameworks f ON f.id = q.framework_id
      WHERE
        a.total_score IS NOT NULL
        AND (:from_ IS NULL OR (
          CASE WHEN :date_basis = 'actual'
            THEN a.actual_start_date
            ELSE a.planned_start_date
          END
        )::date >= :from_)
        AND (:to IS NULL OR (
          CASE WHEN :date_basis = 'actual'
            THEN a.actual_start_date
            ELSE a.planned_start_date
          END
        )::date <= :to)
        AND (:plant IS NULL OR lower(trim(a.plant::text)) = lower(trim(:plant)))
        AND (:data_source = 'monday') = (a.questionnaire_id IS NULL)
        AND (:audit_type_id IS NULL OR q.type_id = :audit_type_id)
    )
    SELECT
      score_calculation,
      questionnaire_name,
      audit_type_value,
      framework_code,
      framework_label
    FROM base;
    """

    rows = db.execute(
        text(sql),
        {
            "from_": from_,
            "to": to,
            "plant": plant, "data_source": data_source,
            "audit_type_id": audit_type_id,
            "date_basis": date_basis,
        },
    ).fetchall()

    profiles = {
        resolve_scoring_profile(
            questionnaire_name=row[1],
            audit_type_value=row[2],
            framework_code=row[3],
            framework_label=row[4],
            score_calculation=row[0],
            is_iatf_nc_mode=False,
        )
        for row in rows
    }

    if len(profiles) == 1:
        return _grade_meta_for_profile(next(iter(profiles)))
    return _grade_meta_for_profile(None)


# ---------------------------------------------------------------------------
# 1 · Audit Hours  (stacked by plant)
# ---------------------------------------------------------------------------

def get_audit_hours(
    db: Session,
    *,
    from_: date | None,
    to: date | None,
    plant: str | None,
    data_source: str = "app",
    audit_type_id: int | None,
    date_basis: str,
    interval: str,
) -> dict[str, Any]:
    """Hours of Audits by date, stacked by plant."""
    _validate_interval(interval)
    _validate_date_basis(date_basis)
    dtu = interval  # 'week' | 'month'
    fmt = _date_trunc_expr(dtu)

    sql = f"""
    WITH base AS (
      SELECT
        CASE WHEN :date_basis = 'actual'
          THEN a.actual_start_date
          ELSE a.planned_start_date
        END AS start_dt,
        CASE WHEN :date_basis = 'actual'
          THEN a.actual_end_date
          ELSE a.planned_end_date
        END AS end_dt,
        lower(trim(a.plant::text)) AS plant
      FROM audits a
      LEFT JOIN questionnaires q ON q.id = a.questionnaire_id
      WHERE
        (:from_ IS NULL OR (
          CASE WHEN :date_basis = 'actual'
            THEN a.actual_start_date
            ELSE a.planned_start_date
          END
        )::date >= :from_)
        AND (:to   IS NULL OR (
          CASE WHEN :date_basis = 'actual'
            THEN a.actual_start_date
            ELSE a.planned_start_date
          END
        )::date <= :to)
        AND (:plant IS NULL OR lower(trim(a.plant::text)) = lower(trim(:plant)))
        AND (:data_source = 'monday') = (a.questionnaire_id IS NULL)
        AND (:audit_type_id IS NULL OR q.type_id = :audit_type_id)
    )
    SELECT
      to_char(date_trunc('{dtu}', start_dt), '{fmt}') AS grp,
      plant                                            AS stack,
      SUM(
        GREATEST(EXTRACT(EPOCH FROM (end_dt - start_dt)) / 3600.0, 0)
      )::numeric(12,2)                                AS value
    FROM base
    WHERE start_dt IS NOT NULL AND end_dt IS NOT NULL
    GROUP BY 1, 2
    ORDER BY 1, 2;
    """

    rows = db.execute(
        text(sql),
        {"from_": from_, "to": to, "plant": plant, "data_source": data_source,
         "audit_type_id": audit_type_id, "date_basis": date_basis},
    ).fetchall()

    result = _pivot_stacked(
        [(r[0], r[1], float(r[2])) for r in rows],
        unit="hours",
        group_by=interval,
        stack_by="plant",
    )
    result["referenceLines"] = AUDIT_HOURS_REFERENCE_LINES
    return result


# ---------------------------------------------------------------------------
# 2 · Late CAR  (stacked by plant)
# ---------------------------------------------------------------------------

def get_late_car(
    db: Session,
    *,
    from_: date | None,
    to: date | None,
    plant: str | None,
    data_source: str = "app",
    interval: str,
) -> dict[str, Any]:
    """Late CARs by period, stacked by plant.

    'Late' = due_date < today AND status is not accepted/closed.
    """
    _validate_interval(interval)
    dtu = interval
    fmt = _date_trunc_expr(dtu)

    sql = f"""
    WITH late AS (
      SELECT
        ca.due_date,
        lower(trim(a.plant::text)) AS plant
      FROM corrective_actions ca
      JOIN audits a ON a.id = ca.audit_id
      WHERE
        ca.due_date IS NOT NULL
        AND ca.due_date < CURRENT_DATE
        AND {_is_open_sql()}
        AND (:from_ IS NULL OR ca.due_date >= :from_)
        AND (:to    IS NULL OR ca.due_date <= :to)
        AND (:plant IS NULL OR lower(trim(a.plant::text)) = lower(trim(:plant)))
        AND (:data_source = 'monday') = (a.questionnaire_id IS NULL)
    )
    SELECT
      to_char(date_trunc('{dtu}', due_date::timestamp), '{fmt}') AS grp,
      plant                                                       AS stack,
      COUNT(*)::int                                               AS value
    FROM late
    GROUP BY 1, 2
    ORDER BY 1, 2;
    """

    rows = db.execute(
        text(sql),
        {"from_": from_, "to": to, "plant": plant, "data_source": data_source},
    ).fetchall()

    return _pivot_stacked(
        [(r[0], r[1], float(r[2])) for r in rows],
        unit="count",
        group_by=interval,
        stack_by="plant",
    )


# ---------------------------------------------------------------------------
# 3 · Audit count + average score  (dual-axis)
# ---------------------------------------------------------------------------

def get_audit_count_and_score(
    db: Session,
    *,
    from_: date | None,
    to: date | None,
    plant: str | None,
    data_source: str = "app",
    audit_type_id: int | None,
    interval: str,
    date_basis: str,
) -> dict[str, Any]:
    """Number of audits (bar) and average score (line), grouped by period."""
    _validate_interval(interval)
    _validate_date_basis(date_basis)
    dtu = interval
    fmt = _date_trunc_expr(dtu)

    sql = f"""
    WITH base AS (
      SELECT
        CASE WHEN :date_basis = 'actual'
          THEN a.actual_start_date
          ELSE a.planned_start_date
        END AS start_dt,
        a.total_score::float AS score
      FROM audits a
      LEFT JOIN questionnaires q ON q.id = a.questionnaire_id
      WHERE
        (:from_ IS NULL OR (
          CASE WHEN :date_basis = 'actual'
            THEN a.actual_start_date
            ELSE a.planned_start_date
          END
        )::date >= :from_)
        AND (:to    IS NULL OR (
          CASE WHEN :date_basis = 'actual'
            THEN a.actual_start_date
            ELSE a.planned_start_date
          END
        )::date <= :to)
        AND (:plant IS NULL OR lower(trim(a.plant::text)) = lower(trim(:plant)))
        AND (:data_source = 'monday') = (a.questionnaire_id IS NULL)
        AND (:audit_type_id IS NULL OR q.type_id = :audit_type_id)
    )
    SELECT
      to_char(date_trunc('{dtu}', start_dt), '{fmt}') AS grp,
      COUNT(*)::int                                    AS audit_count,
      ROUND(AVG(score)::numeric, 4)                   AS avg_score
    FROM base
    WHERE start_dt IS NOT NULL
    GROUP BY 1
    ORDER BY 1;
    """

    rows = db.execute(
        text(sql),
        {"from_": from_, "to": to, "plant": plant, "data_source": data_source,
         "audit_type_id": audit_type_id, "date_basis": date_basis},
    ).fetchall()
    grade_meta = _resolve_score_profile_meta(
        db,
        from_=from_,
        to=to,
        plant=plant,
        data_source=data_source,
        audit_type_id=audit_type_id,
        date_basis=date_basis,
    )

    return {
        "groupBy": interval,
        "unitLeft": "count",
        "unitRight": "score",
        "data": [
            {"group": r[0], "count": int(r[1]), "score": float(r[2] or 0)}
            for r in rows
        ],
        **grade_meta,
    }


# ---------------------------------------------------------------------------
# 3b · Audit status breakdown by period (stacked)
# ---------------------------------------------------------------------------

def get_audit_status_by_period(
    db: Session,
    *,
    from_: date | None,
    to: date | None,
    plant: str | None,
    data_source: str = "app",
    audit_type_id: int | None,
    interval: str,
    date_basis: str,
) -> dict[str, Any]:
    """Audit count by status over time (stacked), filtered by date basis."""
    _validate_interval(interval)
    _validate_date_basis(date_basis)
    dtu = interval
    fmt = _date_trunc_expr(dtu)

    sql = f"""
    WITH base AS (
      SELECT
        CASE WHEN :date_basis = 'actual'
          THEN a.actual_start_date
          ELSE a.planned_start_date
        END AS base_dt,
        a.status::text AS status
      FROM audits a
      LEFT JOIN questionnaires q ON q.id = a.questionnaire_id
      WHERE
        a.status IS NOT NULL
        AND (:plant IS NULL OR lower(trim(a.plant::text)) = lower(trim(:plant)))
        AND (:data_source = 'monday') = (a.questionnaire_id IS NULL)
        AND (:audit_type_id IS NULL OR q.type_id = :audit_type_id)
    )
    SELECT
      to_char(date_trunc('{dtu}', base_dt), '{fmt}') AS grp,
      status                                          AS stack,
      COUNT(*)::int                                   AS value
    FROM base
    WHERE
      base_dt IS NOT NULL
      AND (:from_ IS NULL OR base_dt::date >= :from_)
      AND (:to    IS NULL OR base_dt::date <= :to)
    GROUP BY 1, 2
    ORDER BY 1, 2;
    """

    rows = db.execute(
        text(sql),
        {
            "from_": from_,
            "to": to,
            "plant": plant, "data_source": data_source,
            "audit_type_id": audit_type_id,
            "date_basis": date_basis,
        },
    ).fetchall()

    return _pivot_stacked(
        [(r[0], r[1], float(r[2])) for r in rows],
        unit="count",
        group_by=interval,
        stack_by="audit_status",
    )


# ---------------------------------------------------------------------------
# 3c · Audit status breakdown by plant (stacked)
# ---------------------------------------------------------------------------

def get_audit_status_by_plant(
    db: Session,
    *,
    from_: date | None,
    to: date | None,
    plant: str | None,
    data_source: str = "app",
    audit_type_id: int | None,
    date_basis: str,
) -> dict[str, Any]:
    """Audit count by status per plant (stacked), filtered by date basis."""
    _validate_date_basis(date_basis)

    sql = """
    WITH base AS (
      SELECT
        lower(trim(a.plant::text)) AS plant,
        a.status::text AS status,
        CASE WHEN :date_basis = 'actual'
          THEN a.actual_start_date
          ELSE a.planned_start_date
        END AS base_dt
      FROM audits a
      LEFT JOIN questionnaires q ON q.id = a.questionnaire_id
      WHERE
        a.status IS NOT NULL
        AND a.plant IS NOT NULL
        AND (:plant IS NULL OR lower(trim(a.plant::text)) = lower(trim(:plant)))
        AND (:data_source = 'monday') = (a.questionnaire_id IS NULL)
        AND (:audit_type_id IS NULL OR q.type_id = :audit_type_id)
    )
    SELECT
      plant AS grp,
      status AS stack,
      COUNT(*)::int AS value
    FROM base
    WHERE
      base_dt IS NOT NULL
      AND (:from_ IS NULL OR base_dt::date >= :from_)
      AND (:to    IS NULL OR base_dt::date <= :to)
    GROUP BY 1, 2
    ORDER BY 1, 2;
    """

    rows = db.execute(
        text(sql),
        {
            "from_": from_,
            "to": to,
            "plant": plant, "data_source": data_source,
            "audit_type_id": audit_type_id,
            "date_basis": date_basis,
        },
    ).fetchall()

    return _pivot_stacked(
        [(r[0], r[1], float(r[2])) for r in rows],
        unit="count",
        group_by="plant",
        stack_by="audit_status",
    )


# ---------------------------------------------------------------------------
# 4 · Audits per type per plant  (stacked)
# ---------------------------------------------------------------------------

def get_audits_by_type_and_plant(
    db: Session,
    *,
    from_: date | None,
    to: date | None,
    plant: str | None,
    data_source: str = "app",
    audit_type_id: int | None,
    date_basis: str,
) -> dict[str, Any]:
    """Audit count grouped by plant (x-axis) and audit type (stack)."""
    _validate_date_basis(date_basis)

    sql = """
    WITH base AS (
      SELECT
        lower(trim(a.plant::text)) AS plant,
        at.value::text AS audit_type,
        CASE WHEN :date_basis = 'actual'
          THEN a.actual_start_date
          ELSE a.planned_start_date
        END AS base_dt
      FROM audits a
      LEFT JOIN questionnaires q  ON q.id = a.questionnaire_id
      JOIN audit_types at    ON at.id = q.type_id
      WHERE
        a.plant IS NOT NULL
        AND (:plant IS NULL OR lower(trim(a.plant::text)) = lower(trim(:plant)))
        AND (:data_source = 'monday') = (a.questionnaire_id IS NULL)
        AND (:audit_type_id IS NULL OR q.type_id = :audit_type_id)
    )
    SELECT
      plant AS grp,
      audit_type AS stack,
      COUNT(*)::int AS value
    FROM base
    WHERE
      base_dt IS NOT NULL
      AND (:from_ IS NULL OR base_dt::date >= :from_)
      AND (:to    IS NULL OR base_dt::date <= :to)
    GROUP BY 1, 2
    ORDER BY 1, 2;
    """

    rows = db.execute(
        text(sql),
        {
            "from_": from_,
            "to": to,
            "plant": plant, "data_source": data_source,
            "audit_type_id": audit_type_id,
            "date_basis": date_basis,
        },
    ).fetchall()
    return _pivot_stacked(
        [(r[0], r[1], float(r[2])) for r in rows],
        unit="count",
        group_by="plant",
        stack_by="audit_type",
    )


# ---------------------------------------------------------------------------
# 5 · CAR count by date  (stacked by plant)
# ---------------------------------------------------------------------------

def get_car_count(
    db: Session,
    *,
    from_: date | None,
    to: date | None,
    plant: str | None,
    data_source: str = "app",
    interval: str,
) -> dict[str, Any]:
    """Number of CARs created per period, stacked by plant."""
    _validate_interval(interval)
    dtu = interval
    fmt = _date_trunc_expr(dtu)

    sql = f"""
    SELECT
      to_char(date_trunc('{dtu}', ca.created_at), '{fmt}') AS grp,
      lower(trim(a.plant::text))                                         AS stack,
      COUNT(*)::int                                         AS value
    FROM corrective_actions ca
    JOIN audits a ON a.id = ca.audit_id
    WHERE
      ca.created_at IS NOT NULL
      AND (:from_ IS NULL OR ca.created_at::date >= :from_)
      AND (:to    IS NULL OR ca.created_at::date <= :to)
      AND (:plant IS NULL OR lower(trim(a.plant::text)) = lower(trim(:plant)))
      AND (:data_source = 'monday') = (a.questionnaire_id IS NULL)
    GROUP BY 1, 2
    ORDER BY 1, 2;
    """

    rows = db.execute(text(sql), {"from_": from_, "to": to, "plant": plant, "data_source": data_source}).fetchall()
    return _pivot_stacked(
        [(r[0], r[1], float(r[2])) for r in rows],
        unit="count",
        group_by=interval,
        stack_by="plant",
    )


# ---------------------------------------------------------------------------
# 6 · Average days to close a CAR  (simple time-series)
# ---------------------------------------------------------------------------

def get_avg_days_close_car(
    db: Session,
    *,
    from_: date | None,
    to: date | None,
    plant: str | None,
    data_source: str = "app",
    interval: str,
) -> dict[str, Any]:
    """
    Average calendar days to close a CAR, grouped by creation period.
    Only accepted/closed CARs with a valid submitted_at are included.
    """
    _validate_interval(interval)
    dtu = interval
    fmt = _date_trunc_expr(dtu)

    sql = f"""
    SELECT
      to_char(date_trunc('{dtu}', ca.created_at), '{fmt}')        AS grp,
      ROUND(
        AVG(EXTRACT(EPOCH FROM (ca.submitted_at - ca.created_at))
            / 86400.0)::numeric, 2
      )                                                             AS avg_days
    FROM corrective_actions ca
    JOIN audits a ON a.id = ca.audit_id
    WHERE
      {_is_closed_sql()}
      AND ca.created_at  IS NOT NULL
      AND ca.submitted_at IS NOT NULL
      AND (:from_ IS NULL OR ca.created_at::date >= :from_)
      AND (:to    IS NULL OR ca.created_at::date <= :to)
      AND (:plant IS NULL OR lower(trim(a.plant::text)) = lower(trim(:plant)))
      AND (:data_source = 'monday') = (a.questionnaire_id IS NULL)
    GROUP BY 1
    ORDER BY 1;
    """

    rows = db.execute(text(sql), {"from_": from_, "to": to, "plant": plant, "data_source": data_source}).fetchall()
    result = _simple_series(
        [(r[0], float(r[1] or 0)) for r in rows],
        unit="days",
        group_by=interval,
    )
    result["referenceLines"] = AVG_DAYS_CLOSE_CAR_REFERENCE_LINES
    return result


# ---------------------------------------------------------------------------
# 7 · Average working days to close a CAR, per plant
# ---------------------------------------------------------------------------

def get_working_days_close_car_by_plant(
    db: Session,
    *,
    from_: date | None,
    to: date | None,
    plant: str | None = None,
    data_source: str = "app",
) -> dict[str, Any]:
    """
    Average working days (Mon–Fri) between CAR creation and submission,
    grouped by plant. Only accepted/closed CARs are counted.

    Uses a set-based count instead of generate_series for performance on
    large datasets: working days = calendar days - weekend days.
    Formula:
        working_days = (total_days)
                     - 2 * full_weeks_in_range
                     - adjustment for partial weekend days at both ends
    We use the simpler but correct PostgreSQL idiom:
        SELECT COUNT(*) FROM generate_series(...)
    but materialise it once per CAR, not per row-scan.
    """

    sql = f"""
    WITH closed_cars AS (
      SELECT
        lower(trim(a.plant::text)) AS plant,
        ca.created_at::date  AS start_d,
        ca.submitted_at::date AS end_d
      FROM corrective_actions ca
      JOIN audits a ON a.id = ca.audit_id
      WHERE
        {_is_closed_sql()}
        AND ca.created_at   IS NOT NULL
        AND ca.submitted_at IS NOT NULL
        AND (:from_ IS NULL OR ca.created_at::date >= :from_)
        AND (:to    IS NULL OR ca.created_at::date <= :to)
        AND (:plant IS NULL OR lower(trim(a.plant::text)) = lower(trim(:plant)))
        AND (:data_source = 'monday') = (a.questionnaire_id IS NULL)
        AND a.plant IS NOT NULL
    ),
    with_wdays AS (
      SELECT
        plant,
        -- Efficient working-day count without per-row generate_series:
        -- (days+1) includes both endpoints; subtract 2 per full weekend.
        GREATEST(
          (end_d - start_d + 1)
          - 2 * ((end_d - start_d + 1) / 7)
          - CASE WHEN EXTRACT(ISODOW FROM start_d) = 7 THEN 1 ELSE 0 END
          - CASE WHEN EXTRACT(ISODOW FROM end_d)   = 6 THEN 1 ELSE 0 END,
          0
        )::int AS working_days
      FROM closed_cars
    )
    SELECT
      plant,
      ROUND(AVG(working_days)::numeric, 2) AS avg_working_days
    FROM with_wdays
    GROUP BY 1
    ORDER BY avg_working_days DESC, plant;
    """

    rows = db.execute(text(sql), {"from_": from_, "to": to, "plant": plant, "data_source": data_source}).fetchall()
    result = _category_series(
        [(r[0], float(r[1] or 0)) for r in rows],
        unit="days",
        group_by="plant",
    )
    result["referenceLines"] = WORKING_DAYS_REFERENCE_LINES
    return result


# ---------------------------------------------------------------------------
# 8 · Open CAR count by plant
# ---------------------------------------------------------------------------

def get_open_car_by_plant(
    db: Session,
    *,
    from_: date | None,
    to: date | None,
    plant: str | None,
    data_source: str = "app",
) -> dict[str, Any]:
    """Number of open (non accepted/closed) CARs grouped by plant."""

    sql = f"""
    SELECT
      lower(trim(a.plant::text)) AS plant,
      COUNT(*)::int AS value
    FROM corrective_actions ca
    JOIN audits a ON a.id = ca.audit_id
    WHERE
      {_is_open_sql()}
      AND ca.created_at IS NOT NULL
      AND (:from_ IS NULL OR ca.created_at::date >= :from_)
      AND (:to    IS NULL OR ca.created_at::date <= :to)
      AND (:plant IS NULL OR lower(trim(a.plant::text)) = lower(trim(:plant)))
      AND (:data_source = 'monday') = (a.questionnaire_id IS NULL)
      AND a.plant IS NOT NULL
    GROUP BY 1
    ORDER BY value DESC, plant;
    """

    rows = db.execute(text(sql), {"from_": from_, "to": to, "plant": plant, "data_source": data_source}).fetchall()
    return _category_series(
        [(r[0], float(r[1])) for r in rows],
        unit="count",
        group_by="plant",
    )


# ---------------------------------------------------------------------------
# 9 · Late open CAR count by plant
# ---------------------------------------------------------------------------

def get_late_open_car_by_plant(
    db: Session,
    *,
    from_: date | None,
    to: date | None,
    plant: str | None,
    data_source: str = "app",
) -> dict[str, Any]:
    """Number of late (due_date < today) open CARs grouped by plant."""

    sql = f"""
    SELECT
      lower(trim(a.plant::text)) AS plant,
      COUNT(*)::int AS value
    FROM corrective_actions ca
    JOIN audits a ON a.id = ca.audit_id
    WHERE
      ca.due_date IS NOT NULL
      AND ca.due_date < CURRENT_DATE
      AND {_is_open_sql()}
      AND (:from_ IS NULL OR ca.created_at::date >= :from_)
      AND (:to    IS NULL OR ca.created_at::date <= :to)
      AND (:plant IS NULL OR lower(trim(a.plant::text)) = lower(trim(:plant)))
      AND (:data_source = 'monday') = (a.questionnaire_id IS NULL)
      AND a.plant IS NOT NULL
    GROUP BY 1
    ORDER BY value DESC, plant;
    """

    rows = db.execute(text(sql), {"from_": from_, "to": to, "plant": plant, "data_source": data_source}).fetchall()
    return _category_series(
        [(r[0], float(r[1])) for r in rows],
        unit="count",
        group_by="plant",
    )


# ---------------------------------------------------------------------------
# 10 · Closed-late CAR count by plant
# ---------------------------------------------------------------------------

def get_closed_late_car_by_plant(
    db: Session,
    *,
    from_: date | None,
    to: date | None,
    plant: str | None,
    data_source: str = "app",
) -> dict[str, Any]:
    """
    Number of CARs that are now closed but were submitted late,
    i.e. submitted_at::date > due_date.
    """

    sql = f"""
    SELECT
      lower(trim(a.plant::text)) AS plant,
      COUNT(*)::int AS value
    FROM corrective_actions ca
    JOIN audits a ON a.id = ca.audit_id
    WHERE
      {_is_closed_sql()}
      AND ca.due_date IS NOT NULL
      AND ca.submitted_at IS NOT NULL
      AND ca.submitted_at::date > ca.due_date
      AND (:from_ IS NULL OR ca.submitted_at::date >= :from_)
      AND (:to    IS NULL OR ca.submitted_at::date <= :to)
      AND (:plant IS NULL OR lower(trim(a.plant::text)) = lower(trim(:plant)))
      AND (:data_source = 'monday') = (a.questionnaire_id IS NULL)
      AND a.plant IS NOT NULL
    GROUP BY 1
    ORDER BY value DESC, plant;
    """

    rows = db.execute(text(sql), {"from_": from_, "to": to, "plant": plant, "data_source": data_source}).fetchall()
    return _category_series(
        [(r[0], float(r[1])) for r in rows],
        unit="count",
        group_by="plant",
    )


# ---------------------------------------------------------------------------
# 11 · Open CAR count by audit
# ---------------------------------------------------------------------------

def get_open_car_by_audit(
    db: Session,
    *,
    from_: date | None,
    to: date | None,
    limit: int,
    plant: str | None = None,
    data_source: str = "app",
) -> dict[str, Any]:
    """Top-N audits by number of open CARs."""

    sql = f"""
    SELECT
      a.audit_number::text AS audit_number,
      COUNT(*)::int        AS value
    FROM corrective_actions ca
    JOIN audits a ON a.id = ca.audit_id
    WHERE
      {_is_open_sql()}
      AND ca.created_at IS NOT NULL
      AND a.audit_number IS NOT NULL
      AND (:from_ IS NULL OR ca.created_at::date >= :from_)
      AND (:to    IS NULL OR ca.created_at::date <= :to)
      AND (:plant IS NULL OR lower(trim(a.plant::text)) = lower(trim(:plant)))
      AND (:data_source = 'monday') = (a.questionnaire_id IS NULL)
    GROUP BY 1
    ORDER BY value DESC, audit_number
    LIMIT :limit;
    """

    rows = db.execute(
        text(sql),
        {"from_": from_, "to": to, "limit": limit, "plant": plant, "data_source": data_source},
    ).fetchall()
    return _category_series(
        [(r[0], float(r[1])) for r in rows],
        unit="count",
        group_by="audit",
    )


# ---------------------------------------------------------------------------
# 11 · Audit score by date  (simple time-series, all plants / all types)
# ---------------------------------------------------------------------------

def get_audit_score_by_date(
    db: Session,
    *,
    from_: date | None,
    to: date | None,
    plant: str | None,
    data_source: str = "app",
    audit_type_id: int | None,
    interval: str,
    date_basis: str,
) -> dict[str, Any]:
    """
    Average audit score per period.
    Covers all plants and all audit types unless filtered.
    """
    _validate_interval(interval)
    _validate_date_basis(date_basis)
    dtu = interval
    fmt = _date_trunc_expr(dtu)

    sql = f"""
    WITH base AS (
      SELECT
        CASE WHEN :date_basis = 'actual'
          THEN a.actual_start_date
          ELSE a.planned_start_date
        END AS start_dt,
        a.total_score::float AS score
      FROM audits a
      LEFT JOIN questionnaires q ON q.id = a.questionnaire_id
      WHERE
        a.total_score IS NOT NULL
        AND (:from_ IS NULL OR (
          CASE WHEN :date_basis = 'actual'
            THEN a.actual_start_date
            ELSE a.planned_start_date
          END
        )::date >= :from_)
        AND (:to    IS NULL OR (
          CASE WHEN :date_basis = 'actual'
            THEN a.actual_start_date
            ELSE a.planned_start_date
          END
        )::date <= :to)
        AND (:plant IS NULL OR lower(trim(a.plant::text)) = lower(trim(:plant)))
        AND (:data_source = 'monday') = (a.questionnaire_id IS NULL)
        AND (:audit_type_id IS NULL OR q.type_id = :audit_type_id)
    )
    SELECT
      to_char(date_trunc('{dtu}', start_dt), '{fmt}') AS grp,
      ROUND(AVG(score)::numeric, 4)                   AS avg_score
    FROM base
    WHERE start_dt IS NOT NULL
    GROUP BY 1
    ORDER BY 1;
    """

    rows = db.execute(
        text(sql),
        {"from_": from_, "to": to, "plant": plant, "data_source": data_source,
         "audit_type_id": audit_type_id, "date_basis": date_basis},
    ).fetchall()
    grade_meta = _resolve_score_profile_meta(
        db,
        from_=from_,
        to=to,
        plant=plant,
        data_source=data_source,
        audit_type_id=audit_type_id,
        date_basis=date_basis,
    )

    result = _simple_series(
        [(r[0], float(r[1] or 0)) for r in rows],
        unit="score",
        group_by=interval,
    )
    result.update(grade_meta)
    return result


# ---------------------------------------------------------------------------
# 12 · Average audit score by plant  (category series)
# ---------------------------------------------------------------------------

def get_avg_audit_score_by_plant(
    db: Session,
    *,
    from_: date | None,
    to: date | None,
    plant: str | None,
    data_source: str = "app",
    audit_type_id: int | None,
    date_basis: str,
) -> dict[str, Any]:
    """Average audit total_score grouped by plant."""
    _validate_date_basis(date_basis)

    sql = """
    WITH base AS (
      SELECT
        lower(trim(a.plant::text)) AS plant,
        a.total_score::float AS score,
        CASE WHEN :date_basis = 'actual'
          THEN a.actual_start_date
          ELSE a.planned_start_date
        END AS start_dt
      FROM audits a
      LEFT JOIN questionnaires q ON q.id = a.questionnaire_id
      WHERE
        a.total_score IS NOT NULL
        AND a.plant IS NOT NULL
        AND (:audit_type_id IS NULL OR q.type_id = :audit_type_id)
        AND (:plant IS NULL OR lower(trim(a.plant::text)) = lower(trim(:plant)))
        AND (:data_source = 'monday') = (a.questionnaire_id IS NULL)
    )
    SELECT
      plant,
      ROUND(AVG(score)::numeric, 4) AS avg_score
    FROM base
    WHERE
      start_dt IS NOT NULL
      AND (:from_ IS NULL OR start_dt::date >= :from_)
      AND (:to   IS NULL OR start_dt::date <= :to)
    GROUP BY 1
    ORDER BY avg_score DESC, plant;
    """

    rows = db.execute(
        text(sql),
        {
            "from_": from_,
            "to": to,
            "plant": plant, "data_source": data_source,
            "audit_type_id": audit_type_id,
            "date_basis": date_basis,
        },
    ).fetchall()
    grade_meta = _resolve_score_profile_meta(
        db,
        from_=from_,
        to=to,
        plant=plant,
        data_source=data_source,
        audit_type_id=audit_type_id,
        date_basis=date_basis,
    )

    result = _category_series(
        [(r[0], float(r[1] or 0)) for r in rows],
        unit="score",
        group_by="plant",
    )
    result.update(grade_meta)
    return result


# ---------------------------------------------------------------------------
# 13 · Plant quality overview (audits + CAR totals/closure)
# ---------------------------------------------------------------------------

def get_plant_audit_car_overview(
    db: Session,
    *,
    from_: date | None,
    to: date | None,
    plant: str | None,
    data_source: str = "app",
    audit_type_id: int | None,
    date_basis: str,
) -> dict[str, Any]:
    """
    Plant-level quality overview:
    - total CARs
    - closed CARs
    - audit count
    - average audit score
    - useful quality-manager rates (closure / late-open)
    """
    _validate_date_basis(date_basis)

    sql = f"""
    WITH audits_base AS (
      SELECT
        lower(trim(a.plant::text)) AS plant,
        CASE WHEN :date_basis = 'actual'
          THEN a.actual_start_date
          ELSE a.planned_start_date
        END AS start_dt,
        a.total_score::float AS score
      FROM audits a
      LEFT JOIN questionnaires q ON q.id = a.questionnaire_id
      WHERE
        a.plant IS NOT NULL
        AND (:plant IS NULL OR lower(trim(a.plant::text)) = lower(trim(:plant)))
        AND (:data_source = 'monday') = (a.questionnaire_id IS NULL)
        AND (:audit_type_id IS NULL OR q.type_id = :audit_type_id)
    ),
    audits_by_plant AS (
      SELECT
        plant,
        COUNT(*)::int AS audits,
        ROUND(AVG(score)::numeric, 4) AS avg_score
      FROM audits_base
      WHERE
        start_dt IS NOT NULL
        AND (:from_ IS NULL OR start_dt::date >= :from_)
        AND (:to    IS NULL OR start_dt::date <= :to)
      GROUP BY 1
    ),
    cars_by_plant AS (
      SELECT
        lower(trim(a.plant::text)) AS plant,
        COUNT(*)::int AS total_cars,
        COUNT(*) FILTER (WHERE {_is_closed_sql()})::int AS closed_cars,
        COUNT(*) FILTER (WHERE {_is_open_sql()})::int AS open_cars,
        COUNT(*) FILTER (
          WHERE ca.due_date IS NOT NULL
            AND ca.due_date < CURRENT_DATE
            AND {_is_open_sql()}
        )::int AS late_open_cars
      FROM corrective_actions ca
      JOIN audits a ON a.id = ca.audit_id
      LEFT JOIN questionnaires q ON q.id = a.questionnaire_id
      WHERE
        a.plant IS NOT NULL
        AND ca.created_at IS NOT NULL
        AND (:from_ IS NULL OR ca.created_at::date >= :from_)
        AND (:to    IS NULL OR ca.created_at::date <= :to)
        AND (:plant IS NULL OR lower(trim(a.plant::text)) = lower(trim(:plant)))
        AND (:data_source = 'monday') = (a.questionnaire_id IS NULL)
        AND (:audit_type_id IS NULL OR q.type_id = :audit_type_id)
      GROUP BY 1
    )
    SELECT
      COALESCE(abp.plant, cbp.plant) AS plant,
      COALESCE(cbp.total_cars, 0)    AS total_cars,
      COALESCE(cbp.closed_cars, 0)   AS closed_cars,
      COALESCE(cbp.open_cars, 0)     AS open_cars,
      COALESCE(cbp.late_open_cars, 0) AS late_open_cars,
      COALESCE(abp.audits, 0)        AS audits,
      abp.avg_score                  AS avg_score
    FROM audits_by_plant abp
    FULL OUTER JOIN cars_by_plant cbp ON cbp.plant = abp.plant
    ORDER BY 1;
    """

    rows = db.execute(
        text(sql),
        {
            "from_": from_,
            "to": to,
            "plant": plant, "data_source": data_source,
            "audit_type_id": audit_type_id,
            "date_basis": date_basis,
        },
    ).fetchall()
    grade_meta = _resolve_score_profile_meta(
        db,
        from_=from_,
        to=to,
        plant=plant,
        data_source=data_source,
        audit_type_id=audit_type_id,
        date_basis=date_basis,
    )

    details = []
    grouped_data = []
    audit_score_data = []

    for r in rows:
        plant_name = r[0]
        total_cars = int(r[1] or 0)
        closed_cars = int(r[2] or 0)
        open_cars = int(r[3] or 0)
        late_open_cars = int(r[4] or 0)
        audits = int(r[5] or 0)
        avg_score = float(r[6]) if r[6] is not None else None

        details.append(
            {
                "group": plant_name,
                "totalCars": total_cars,
                "closedCars": closed_cars,
                "openCars": open_cars,
                "lateOpenCars": late_open_cars,
                "audits": audits,
                "avgScore": round(avg_score, 4) if avg_score is not None else None,
                "closureRate": _safe_pct(closed_cars, total_cars),
                "lateOpenRate": _safe_pct(late_open_cars, total_cars),
            }
        )
        grouped_data.append(
            {
                "group": plant_name,
                "totalCars": total_cars,
                "closedCars": closed_cars,
                "openCars": open_cars,
                "lateOpenCars": late_open_cars,
                "audits": audits,
            }
        )
        if avg_score is not None:
            audit_score_data.append(
                {
                    "group": plant_name,
                    "count": audits,
                    "score": round(avg_score, 4),
                }
            )

    return {
        "groupBy": "plant",
        "groupedMetrics": {
            "unit": "count",
            "keys": ["totalCars", "closedCars", "openCars", "lateOpenCars", "audits"],
            "data": grouped_data,
        },
        "auditCountScoreByPlant": {
            "groupBy": "plant",
            "unitLeft": "count",
            "unitRight": "score",
            "data": audit_score_data,
            **grade_meta,
        },
        "details": details,
    }


# ---------------------------------------------------------------------------
# 14 · Average score by focus type
# ---------------------------------------------------------------------------

def get_avg_score_by_focus_type(
    db: Session,
    *,
    from_: date | None,
    to: date | None,
    plant: str | None,
    data_source: str = "app",
    audit_type_id: int | None,
    date_basis: str,
) -> dict[str, Any]:
    """
    Average score by requested audit focus groups:
      - vda
      - plantManagerIATF
      - isoIatf
      - usageOfGlasses
    """
    _validate_date_basis(date_basis)

    sql = """
    WITH base AS (
      SELECT
        CASE
          WHEN lower(coalesce(at.value, '')) LIKE '%plant%manager%iatf%'
            OR lower(coalesce(at.value, '')) LIKE '%plant%manager%'
            THEN 'plantManagerIATF'
          WHEN lower(coalesce(at.value, '')) LIKE '%usage%glasses%'
            OR lower(coalesce(at.value, '')) LIKE '%glasses%'
            OR lower(coalesce(q.name, '')) LIKE '%usage%glasses%'
            OR lower(coalesce(q.name, '')) LIKE '%use%of%glasses%'
            THEN 'usageOfGlasses'
          WHEN lower(coalesce(at.value, '')) LIKE '%vda%'
            OR lower(coalesce(at.value, '')) LIKE '%process%'
            THEN 'vda'
          WHEN lower(coalesce(at.value, '')) LIKE '%quality%'
            OR lower(coalesce(at.value, '')) LIKE '%iatf%'
            OR lower(coalesce(at.value, '')) LIKE '%iso%'
            THEN 'isoIatf'
          WHEN lower(coalesce(f.label, '')) LIKE '%vda%'
            OR lower(coalesce(f.code, '')) LIKE '%vda%'
            THEN 'vda'
          WHEN (
            lower(coalesce(f.label, '')) LIKE '%internal%'
            OR lower(coalesce(f.code, '')) LIKE '%internal%'
          ) AND lower(coalesce(q.name, '')) LIKE '%plant%manager%'
            THEN 'plantManagerIATF'
          WHEN (
            lower(coalesce(f.label, '')) LIKE '%internal%'
            OR lower(coalesce(f.code, '')) LIKE '%internal%'
          ) AND (
            lower(coalesce(q.name, '')) LIKE '%usage%glasses%'
            OR lower(coalesce(q.name, '')) LIKE '%use%of%glasses%'
          ) THEN 'usageOfGlasses'
          WHEN lower(coalesce(f.label, '')) LIKE '%iatf%'
            OR lower(coalesce(f.code, '')) LIKE '%iatf%'
            OR lower(coalesce(f.label, '')) LIKE '%iso%'
            OR lower(coalesce(f.code, '')) LIKE '%iso%'
            THEN 'isoIatf'
          ELSE NULL
        END AS focus_type,
        a.total_score::float AS score,
        CASE WHEN :date_basis = 'actual'
          THEN a.actual_start_date
          ELSE a.planned_start_date
        END AS start_dt
      FROM audits a
      LEFT JOIN questionnaires q ON q.id = a.questionnaire_id
      LEFT JOIN audit_types at ON at.id = q.type_id
      JOIN frameworks f ON f.id = q.framework_id
      WHERE
        a.total_score IS NOT NULL
        AND a.plant IS NOT NULL
        AND (:plant IS NULL OR lower(trim(a.plant::text)) = lower(trim(:plant)))
        AND (:data_source = 'monday') = (a.questionnaire_id IS NULL)
        AND (:audit_type_id IS NULL OR q.type_id = :audit_type_id)
    )
    SELECT
      focus_type,
      COUNT(*)::int AS audits,
      ROUND(AVG(score)::numeric, 4) AS avg_score
    FROM base
    WHERE
      focus_type IS NOT NULL
      AND start_dt IS NOT NULL
      AND (:from_ IS NULL OR start_dt::date >= :from_)
      AND (:to    IS NULL OR start_dt::date <= :to)
    GROUP BY 1;
    """

    rows = db.execute(
        text(sql),
        {
            "from_": from_,
            "to": to,
            "plant": plant, "data_source": data_source,
            "audit_type_id": audit_type_id,
            "date_basis": date_basis,
        },
    ).fetchall()
    grade_meta = _resolve_score_profile_meta(
        db,
        from_=from_,
        to=to,
        plant=plant,
        data_source=data_source,
        audit_type_id=audit_type_id,
        date_basis=date_basis,
    )

    by_type: dict[str, dict[str, float]] = {
        t: {"audits": 0.0, "avg_score": 0.0} for t in _FOCUS_TYPE_ORDER
    }
    for focus_type, audits, avg_score in rows:
        if focus_type in by_type:
            by_type[focus_type] = {
                "audits": float(audits or 0),
                "avg_score": float(avg_score or 0),
            }

    return {
        "groupBy": "focus_type",
        "unit": "score",
        "data": [
            {"group": t, "value": round(by_type[t]["avg_score"], 4)}
            for t in _FOCUS_TYPE_ORDER
        ],
        "auditCounts": [
            {"group": t, "value": int(by_type[t]["audits"])}
            for t in _FOCUS_TYPE_ORDER
        ],
        **grade_meta,
    }


# ---------------------------------------------------------------------------
# 15 · Average score by audit type and plant (for selected period)
# ---------------------------------------------------------------------------

def get_avg_score_by_type_and_plant(
    db: Session,
    *,
    from_: date | None,
    to: date | None,
    plant: str | None,
    data_source: str = "app",
    audit_type_id: int | None,
    date_basis: str,
) -> dict[str, Any]:
    """Average audit score grouped by plant (x-axis) and audit type (series)."""
    _validate_date_basis(date_basis)

    sql = """
    WITH base AS (
      SELECT
        lower(trim(a.plant::text)) AS plant,
        at.value::text AS audit_type,
        a.total_score::float AS score,
        CASE WHEN :date_basis = 'actual'
          THEN a.actual_start_date
          ELSE a.planned_start_date
        END AS start_dt
      FROM audits a
      LEFT JOIN questionnaires q ON q.id = a.questionnaire_id
      JOIN audit_types at ON at.id = q.type_id
      WHERE
        a.total_score IS NOT NULL
        AND a.plant IS NOT NULL
        AND (:plant IS NULL OR lower(trim(a.plant::text)) = lower(trim(:plant)))
        AND (:data_source = 'monday') = (a.questionnaire_id IS NULL)
        AND (:audit_type_id IS NULL OR q.type_id = :audit_type_id)
    )
    SELECT
      plant AS grp,
      audit_type AS stack,
      ROUND(AVG(score)::numeric, 4) AS value
    FROM base
    WHERE
      start_dt IS NOT NULL
      AND (:from_ IS NULL OR start_dt::date >= :from_)
      AND (:to   IS NULL OR start_dt::date <= :to)
    GROUP BY 1, 2
    ORDER BY 1, 2;
    """

    rows = db.execute(
        text(sql),
        {
            "from_": from_,
            "to": to,
            "plant": plant, "data_source": data_source,
            "audit_type_id": audit_type_id,
            "date_basis": date_basis,
        },
    ).fetchall()

    return _pivot_stacked(
        [(r[0], r[1], float(r[2] or 0)) for r in rows],
        unit="score",
        group_by="plant",
        stack_by="audit_type",
    )


# ---------------------------------------------------------------------------
# 16 · Planned audits vs execution/report creation (created_at)
# ---------------------------------------------------------------------------

def get_planned_vs_execution(
    db: Session,
    *,
    from_: date | None,
    to: date | None,
    plant: str | None,
    data_source: str = "app",
    audit_type_id: int | None,
    interval: str,
    date_basis: str,
) -> dict[str, Any]:
    """
    Compare:
    - audits planned in each period (planned_start_date)
    - audits actual in each period (actual_start_date)
    - audits executed/reported in each period (created_at)
    - average delay in days between selected baseline date and created_at
      (grouped by selected baseline period)
    """
    _validate_interval(interval)
    _validate_date_basis(date_basis)
    dtu = interval
    fmt = _date_trunc_expr(dtu)

    sql = f"""
    WITH base AS (
      SELECT
        a.planned_start_date AS planned_dt,
        a.actual_start_date  AS actual_dt,
        CASE WHEN :date_basis = 'actual'
          THEN a.actual_start_date
          ELSE a.planned_start_date
        END AS baseline_dt,
        a.created_at         AS report_dt,
        lower(trim(a.plant::text)) AS plant,
        q.type_id            AS audit_type_id
      FROM audits a
      LEFT JOIN questionnaires q ON q.id = a.questionnaire_id
      WHERE
        (:plant IS NULL OR lower(trim(a.plant::text)) = lower(trim(:plant)))
        AND (:data_source = 'monday') = (a.questionnaire_id IS NULL)
        AND (:audit_type_id IS NULL OR q.type_id = :audit_type_id)
    ),
    planned AS (
      SELECT
        to_char(date_trunc('{dtu}', planned_dt), '{fmt}') AS grp,
        COUNT(*)::int                                     AS planned_count
      FROM base
      WHERE
        planned_dt IS NOT NULL
        AND (:from_ IS NULL OR planned_dt::date >= :from_)
        AND (:to    IS NULL OR planned_dt::date <= :to)
      GROUP BY 1
    ),
    actual AS (
      SELECT
        to_char(date_trunc('{dtu}', actual_dt), '{fmt}') AS grp,
        COUNT(*)::int                                   AS actual_count
      FROM base
      WHERE
        actual_dt IS NOT NULL
        AND (:from_ IS NULL OR actual_dt::date >= :from_)
        AND (:to    IS NULL OR actual_dt::date <= :to)
      GROUP BY 1
    ),
    executed AS (
      SELECT
        to_char(date_trunc('{dtu}', report_dt), '{fmt}') AS grp,
        COUNT(*)::int                                    AS executed_count
      FROM base
      WHERE
        report_dt IS NOT NULL
        AND (:from_ IS NULL OR report_dt::date >= :from_)
        AND (:to    IS NULL OR report_dt::date <= :to)
      GROUP BY 1
    ),
    delay AS (
      SELECT
        to_char(date_trunc('{dtu}', baseline_dt), '{fmt}') AS grp,
        ROUND(
          AVG(
            EXTRACT(EPOCH FROM (report_dt - baseline_dt)) / 86400.0
          )::numeric,
          2
        ) AS avg_delay_days
      FROM base
      WHERE
        baseline_dt IS NOT NULL
        AND report_dt IS NOT NULL
        AND (:from_ IS NULL OR baseline_dt::date >= :from_)
        AND (:to    IS NULL OR baseline_dt::date <= :to)
      GROUP BY 1
    ),
    all_groups AS (
      SELECT grp FROM planned
      UNION
      SELECT grp FROM actual
      UNION
      SELECT grp FROM executed
    )
    SELECT
      g.grp,
      COALESCE(p.planned_count, 0)  AS planned_count,
      COALESCE(a.actual_count, 0)   AS actual_count,
      COALESCE(e.executed_count, 0) AS executed_count,
      COALESCE(d.avg_delay_days, 0) AS avg_delay_days
    FROM all_groups g
    LEFT JOIN planned  p ON p.grp = g.grp
    LEFT JOIN actual   a ON a.grp = g.grp
    LEFT JOIN executed e ON e.grp = g.grp
    LEFT JOIN delay    d ON d.grp = g.grp
    ORDER BY g.grp;
    """

    rows = db.execute(
        text(sql),
        {
            "from_": from_,
            "to": to,
            "plant": plant, "data_source": data_source,
            "audit_type_id": audit_type_id,
            "date_basis": date_basis,
        },
    ).fetchall()

    return {
        "groupBy": interval,
        "unitLeft": "count",
        "unitRight": "days",
        "data": [
            {
                "group": r[0],
                "planned": int(r[1] or 0),
                "actual": int(r[2] or 0),
                "executed": int(r[3] or 0),
                "delayDays": float(r[4] or 0),
            }
            for r in rows
        ],
    }


# ---------------------------------------------------------------------------
# Auditor performance – audits run, avg score, and CAR outcomes per auditor
# ---------------------------------------------------------------------------

def get_auditor_performance(
    db: Session,
    *,
    from_: date | None = None,
    to: date | None = None,
    auditor_id: int | None = None,
) -> dict[str, Any]:
    """Per-auditor breakdown: audits run, average score, and the CAR outcomes
    (open / late-open / closed-late) generated by those audits."""

    sql = f"""
    SELECT
      u.id                                    AS auditor_id,
      trim(concat(u.first_name, ' ', u.last_name)) AS auditor_name,
      COUNT(DISTINCT a.id)::int                AS audit_count,
      ROUND(AVG(a.total_score)::numeric, 2)    AS avg_score,
      COUNT(DISTINCT ca.id) FILTER (WHERE {_is_open_sql()})::int AS open_cars,
      COUNT(DISTINCT ca.id) FILTER (
        WHERE ca.due_date IS NOT NULL AND ca.due_date < CURRENT_DATE AND {_is_open_sql()}
      )::int AS late_open_cars,
      COUNT(DISTINCT ca.id) FILTER (
        WHERE {_is_closed_sql()} AND ca.due_date IS NOT NULL
          AND ca.submitted_at IS NOT NULL AND ca.submitted_at::date > ca.due_date
      )::int AS closed_late_cars
    FROM audits a
    JOIN users u ON u.id = a.auditor_id
    LEFT JOIN corrective_actions ca ON ca.audit_id = a.id
    WHERE
      (:from_ IS NULL OR a.planned_start_date::date >= :from_)
      AND (:to IS NULL OR a.planned_start_date::date <= :to)
      AND (:auditor_id IS NULL OR u.id = :auditor_id)
    GROUP BY u.id, auditor_name
    ORDER BY audit_count DESC, auditor_name;
    """

    rows = db.execute(
        text(sql),
        {"from_": from_, "to": to, "auditor_id": auditor_id},
    ).fetchall()

    return {
        "groupBy": "auditor",
        "details": [
            {
                "auditorId": r[0],
                "auditorName": r[1],
                "auditCount": int(r[2] or 0),
                "avgScore": float(r[3]) if r[3] is not None else None,
                "openCars": int(r[4] or 0),
                "lateOpenCars": int(r[5] or 0),
                "closedLateCars": int(r[6] or 0),
            }
            for r in rows
        ],
    }


# ---------------------------------------------------------------------------
# Repetitive findings – same question failing across multiple audits
# ---------------------------------------------------------------------------

def get_repetitive_findings(
    db: Session,
    *,
    plant: str | None = None,
    from_: date | None = None,
    to: date | None = None,
    min_occurrences: int = 2,
) -> dict[str, Any]:
    """Findings (by question) that recur across multiple audits — surfaces
    systemic/repetitive non-conformities rather than one-off issues."""

    sql = """
    SELECT
      lower(trim(a.plant::text)) AS plant,
      q.id                       AS question_id,
      q.description              AS question,
      COUNT(*)::int              AS occurrences,
      array_agg(DISTINCT a.audit_number ORDER BY a.audit_number) AS audit_numbers
    FROM audit_answers aa
    JOIN audits a ON a.id = aa.audit_id
    JOIN questions q ON q.id = aa.question_id
    WHERE
      aa.fail IS TRUE
      AND (:plant IS NULL OR lower(trim(a.plant::text)) = lower(trim(:plant)))
      AND (:from_ IS NULL OR a.planned_start_date::date >= :from_)
      AND (:to IS NULL OR a.planned_start_date::date <= :to)
    GROUP BY 1, 2, 3
    HAVING COUNT(*) >= :min_occurrences
    ORDER BY occurrences DESC, plant
    LIMIT 50;
    """

    rows = db.execute(
        text(sql),
        {
            "plant": plant,
            "from_": from_,
            "to": to,
            "min_occurrences": min_occurrences,
        },
    ).fetchall()

    return {
        "groupBy": "plant_question",
        "details": [
            {
                "plant": r[0],
                "questionId": r[1],
                "question": r[2],
                "occurrences": int(r[3] or 0),
                "auditNumbers": list(r[4] or []),
            }
            for r in rows
        ],
    }


# ---------------------------------------------------------------------------
# Row-level open CAR list — plant, auditee, due date per CAR (not an aggregate)
# ---------------------------------------------------------------------------

def get_open_cars_detail(
    db: Session,
    *,
    plant: str | None = None,
    from_: date | None = None,
    to: date | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Row-level list of currently open CARs with plant, auditee, status, and
    due date — for when a manager wants the actual CAR list, not just an
    aggregate count."""

    sql = f"""
    SELECT
      ca.id AS car_id,
      ca.identifier AS identifier,
      a.audit_number AS audit_number,
      lower(trim(a.plant::text)) AS plant,
      au.email AS auditee_email,
      ca.status::text AS status,
      ca.due_date AS due_date,
      (ca.due_date IS NOT NULL AND ca.due_date < CURRENT_DATE) AS is_overdue
    FROM corrective_actions ca
    JOIN audits a ON a.id = ca.audit_id
    LEFT JOIN audit_auditees au ON au.id = ca.auditee_id
    WHERE
      {_is_open_sql()}
      AND (:plant IS NULL OR lower(trim(a.plant::text)) = lower(trim(:plant)))
      AND (:from_ IS NULL OR ca.created_at::date >= :from_)
      AND (:to IS NULL OR ca.created_at::date <= :to)
      AND a.plant IS NOT NULL
    ORDER BY ca.due_date NULLS LAST, plant
    LIMIT :limit;
    """

    rows = db.execute(
        text(sql),
        {"plant": plant, "from_": from_, "to": to, "limit": limit},
    ).fetchall()

    return {
        "groupBy": "car",
        "details": [
            {
                "carId": r[0],
                "identifier": r[1],
                "auditNumber": r[2],
                "plant": r[3],
                "auditeeEmail": r[4],
                "status": r[5],
                "dueDate": r[6].isoformat() if r[6] else None,
                "isOverdue": bool(r[7]),
            }
            for r in rows
        ],
    }


# ---------------------------------------------------------------------------
# Findings by severity classification (Major / Minor / Improvement / Strong Point)
# ---------------------------------------------------------------------------

def get_findings_by_classification(
    db: Session,
    *,
    classification: str = "Major",
    plant: str | None = None,
    auditor_id: int | None = None,
    from_: date | None = None,
    to: date | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Row-level list of findings at a given severity classification
    (default 'Major'), with plant, auditor, audit number, question, and
    finding text — for identifying the major non-conformities auditors have
    actually raised, as opposed to CAR-status or recurrence metrics."""

    sql = """
    SELECT
      a.audit_number                AS audit_number,
      lower(trim(a.plant::text))    AS plant,
      u.email                       AS auditor_email,
      q.description                 AS question,
      aa.finding_text                AS finding_text,
      aa.classification              AS classification,
      aa.standard_paragraph          AS standard_paragraph,
      a.planned_start_date           AS audit_date
    FROM audit_answers aa
    JOIN audits a ON a.id = aa.audit_id
    LEFT JOIN questions q ON q.id = aa.question_id
    LEFT JOIN users u ON u.id = a.auditor_id
    WHERE
      lower(trim(aa.classification)) = lower(trim(:classification))
      AND (:plant IS NULL OR lower(trim(a.plant::text)) = lower(trim(:plant)))
      AND (:auditor_id IS NULL OR u.id = :auditor_id)
      AND (:from_ IS NULL OR a.planned_start_date::date >= :from_)
      AND (:to IS NULL OR a.planned_start_date::date <= :to)
    ORDER BY a.planned_start_date DESC NULLS LAST
    LIMIT :limit;
    """

    rows = db.execute(
        text(sql),
        {
            "classification": classification,
            "plant": plant,
            "auditor_id": auditor_id,
            "from_": from_,
            "to": to,
            "limit": limit,
        },
    ).fetchall()

    return {
        "groupBy": "finding",
        "details": [
            {
                "auditNumber": r[0],
                "plant": r[1],
                "auditorEmail": r[2],
                "question": r[3],
                "findingText": r[4],
                "classification": r[5],
                "standardParagraph": r[6],
                "auditDate": r[7].isoformat() if r[7] else None,
            }
            for r in rows
        ],
    }


# ---------------------------------------------------------------------------
# Auditor CAR-review turnaround — time between auditee submission and the
# auditor's accept/reject decision
# ---------------------------------------------------------------------------

def get_auditor_review_turnaround(
    db: Session,
    *,
    auditor_id: int | None = None,
    from_: date | None = None,
    to: date | None = None,
) -> dict[str, Any]:
    """Per-auditor CAR review responsiveness: average/max days between an
    auditee's CAR submission and the auditor's accept/reject decision, plus
    how many reviews took more than 3 days. Note: uses the CAR's current
    submitted_at, so a CAR resubmitted after rejection reflects only its
    latest submission cycle."""

    sql = """
    SELECT
      u.id AS auditor_id,
      trim(concat(u.first_name, ' ', u.last_name)) AS auditor_name,
      COUNT(*)::int AS reviews_count,
      ROUND(AVG(EXTRACT(EPOCH FROM (h.reviewed_at - ca.submitted_at)) / 86400.0)::numeric, 2) AS avg_turnaround_days,
      ROUND(MAX(EXTRACT(EPOCH FROM (h.reviewed_at - ca.submitted_at)) / 86400.0)::numeric, 2) AS max_turnaround_days,
      COUNT(*) FILTER (
        WHERE EXTRACT(EPOCH FROM (h.reviewed_at - ca.submitted_at)) / 86400.0 > 3
      )::int AS reviews_over_3_days
    FROM corrective_action_history h
    JOIN corrective_actions ca ON ca.id = h.corrective_action_id
    JOIN users u ON u.id = h.auditor_id
    WHERE
      h.reviewed_at IS NOT NULL
      AND ca.submitted_at IS NOT NULL
      AND (:auditor_id IS NULL OR u.id = :auditor_id)
      AND (:from_ IS NULL OR h.reviewed_at::date >= :from_)
      AND (:to IS NULL OR h.reviewed_at::date <= :to)
    GROUP BY u.id, auditor_name
    ORDER BY avg_turnaround_days DESC NULLS LAST;
    """

    rows = db.execute(
        text(sql),
        {"auditor_id": auditor_id, "from_": from_, "to": to},
    ).fetchall()

    return {
        "groupBy": "auditor",
        "details": [
            {
                "auditorId": r[0],
                "auditorName": r[1],
                "reviewsCount": int(r[2] or 0),
                "avgTurnaroundDays": float(r[3]) if r[3] is not None else None,
                "maxTurnaroundDays": float(r[4]) if r[4] is not None else None,
                "reviewsOver3Days": int(r[5] or 0),
            }
            for r in rows
        ],
    }


# ---------------------------------------------------------------------------
# Row-level slow CAR reviews — the actual CARs that took an auditor a long
# time to review, not just an aggregate
# ---------------------------------------------------------------------------

def get_slow_car_reviews(
    db: Session,
    *,
    auditor_id: int | None = None,
    min_days: float = 3,
    from_: date | None = None,
    to: date | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Row-level list of CAR reviews that took longer than min_days between
    the auditee's submission and the auditor's decision."""

    sql = """
    SELECT
      ca.id AS car_id,
      ca.identifier AS identifier,
      a.audit_number AS audit_number,
      lower(trim(a.plant::text)) AS plant,
      u.email AS auditor_email,
      ca.submitted_at AS submitted_at,
      h.reviewed_at AS reviewed_at,
      ROUND((EXTRACT(EPOCH FROM (h.reviewed_at - ca.submitted_at)) / 86400.0)::numeric, 2) AS days_taken,
      h.decision::text AS decision
    FROM corrective_action_history h
    JOIN corrective_actions ca ON ca.id = h.corrective_action_id
    JOIN audits a ON a.id = ca.audit_id
    JOIN users u ON u.id = h.auditor_id
    WHERE
      h.reviewed_at IS NOT NULL
      AND ca.submitted_at IS NOT NULL
      AND EXTRACT(EPOCH FROM (h.reviewed_at - ca.submitted_at)) / 86400.0 >= :min_days
      AND (:auditor_id IS NULL OR u.id = :auditor_id)
      AND (:from_ IS NULL OR h.reviewed_at::date >= :from_)
      AND (:to IS NULL OR h.reviewed_at::date <= :to)
    ORDER BY days_taken DESC
    LIMIT :limit;
    """

    rows = db.execute(
        text(sql),
        {
            "auditor_id": auditor_id,
            "min_days": min_days,
            "from_": from_,
            "to": to,
            "limit": limit,
        },
    ).fetchall()

    return {
        "groupBy": "car_review",
        "details": [
            {
                "carId": r[0],
                "identifier": r[1],
                "auditNumber": r[2],
                "plant": r[3],
                "auditorEmail": r[4],
                "submittedAt": r[5].isoformat() if r[5] else None,
                "reviewedAt": r[6].isoformat() if r[6] else None,
                "daysTaken": float(r[7]) if r[7] is not None else None,
                "decision": r[8],
            }
            for r in rows
        ],
    }


