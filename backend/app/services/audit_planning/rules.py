"""Pure rule engine for the monthly audit plan - no DB, no network.

Everything here takes plain dataclasses (built by sources.py) and returns
plain dataclasses, so the P1-P11 logic and the capacity scheduler can be
unit-tested without any of the three source databases.

Rules confirmed with the business owner (2026-09-24):
- P1 = complaint not closed on time: still open and past its due date or
  with an overdue 8D step, or closed last month after its due date.
- P4 counts all complaints last month; P5 = the same complaint repeated 2+
  times in the same month (see P5_MATCH_FIELDS - PROVISIONAL, the owner was
  not sure how a repeat is recorded; `repetitive_complete_with_number` turned
  out to be a hand-typed count that doesn't track real repeats).
- P4 and P5 firing on the same plant/line produce ONE merged audit.
- P8 fires when the external IATF audit IS due within 4 months (Y), and then
  covers each support process not audited internally in the last 4 months.
- P11 = any of NQC / scrap / PPM over target last month, no tiering.
- "Line" = plant + complaints.product_line.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

# ─────────────────────────────────────────────────────────────
# Reference data
# ─────────────────────────────────────────────────────────────

# Canonical plant keys are this app's plant_type enum values. Monday's
# "Kunshan+Anhui" is one weekly slot shared by the two plants, so the weekly
# target is applied per slot group, not per plant.
SCHEDULE_GROUPS: dict[str, tuple[int, tuple[str, ...]]] = {
    # group key: (weekday, plants)   weekday: 0 = Monday
    "kunshan_anhui": (0, ("kunshan", "anhui")),
    "atlas": (0, ("atlas",)),
    "frankfort": (1, ("frankfort",)),
    "monterrey": (1, ("monterrey",)),
    "carthage": (2, ("carthage",)),
    "loire": (2, ("loire",)),
    "poitiers": (3, ("poitiers",)),
    "daegu": (3, ("daegu",)),
    "tianjin": (4, ("tianjin",)),
    "chennai": (4, ("chennai",)),
}
PLANT_GROUP: dict[str, str] = {
    plant: group for group, (_, plants) in SCHEDULE_GROUPS.items() for plant in plants
}
SCHEDULED_PLANTS: tuple[str, ...] = tuple(PLANT_GROUP)

# Spellings seen in the source systems -> canonical plant key. Anything after
# a "/" is dropped first ("ATLAS/Tunisia" -> "atlas").
PLANT_ALIASES: dict[str, str] = {
    "frankfurt": "frankfort",
    "korea": "daegu",
}

# Complaints use ASSEMBLY/CHOKE/BRUSH, projects use Assemblies/ASY etc.
PRODUCT_LINE_ALIASES: dict[str, str] = {
    "assemblies": "assembly",
    "asy": "assembly",
    "chokes": "choke",
    "cho": "choke",
    "brushes": "brush",
    "bru": "brush",
}

# Complaint statuses that never count (live statuses are D1..D8/open/closed).
IGNORED_COMPLAINT_STATUSES = {"cancelled", "rejected"}

P4_COMPLAINT_THRESHOLD = 3          # > 3 complaints last month
# P5 (PROVISIONAL): complaints opened last month that share all of these
# fields count as one repeated complaint. A blank value or a defect of "NA"
# never matches.
P5_MATCH_FIELDS = ("plant", "product_line", "customer", "defect")
P5_MIN_REPEATS = 2
SOP_HORIZON_MONTHS = 5              # P6
PLANT_MANAGER_WINDOW_MONTHS = 3     # P7
EXTERNAL_AUDIT_HORIZON_MONTHS = 4   # P8, P10
SUPPORT_PROCESS_WINDOW_MONTHS = 4   # P8
RECOVERY_PLAN_WINDOW_MONTHS = 3     # P9
LINE_REAUDIT_WINDOW_MONTHS = 3      # capacity rule
VOLUME_WINDOW_MONTHS = 12           # "top offenders" ranking

# Who gets audited for each check (role names as they exist in the roles MCP).
# "Process owner" is not a role in the MCP, so P8 always needs manual assignment.
AUDITEE_ROLE = {
    "P1": "Quality engineers",
    "P2": "Quality manager",
    "P3": "Quality manager",
    # the process owner for customer complaints
    "P4": "Quality manager",
    "P5": "Quality engineers",
    "P6": "Project manager",
    "P7": "Plant manager",
    "P8": "Process owner",
    "P9": "Plant manager",
    "P10": "Quality manager",
    "P11": "Quality manager",
}

HISTORY_LINE = "line"
HISTORY_PLANT_MANAGER = "plant_manager"
HISTORY_SUPPORT_PROCESS = "support_process"
HISTORY_RECOVERY_PLAN = "recovery_plan"
HISTORY_ISO14001 = "iso14001"
HISTORY_QUALITY_METRICS = "quality_metrics"
HISTORY_KINDS = (
    HISTORY_LINE,
    HISTORY_PLANT_MANAGER,
    HISTORY_SUPPORT_PROCESS,
    HISTORY_RECOVERY_PLAN,
    HISTORY_ISO14001,
    HISTORY_QUALITY_METRICS,
)

STATUS_SCHEDULED = "scheduled"
STATUS_OVER_CAPACITY = "over_capacity"
STATUS_SUPPRESSED_RECENT = "suppressed_recent"


def normalize_plant(value: Optional[str]) -> Optional[str]:
    key = (value or "").split("/")[0].strip().lower()
    if not key:
        return None
    return PLANT_ALIASES.get(key, key)


def normalize_product_line(value: Optional[str]) -> Optional[str]:
    key = (value or "").strip().lower()
    if not key:
        return None
    return PRODUCT_LINE_ALIASES.get(key, key)


def add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def month_bounds(first_of_month: date) -> tuple[date, date]:
    last_day = calendar.monthrange(first_of_month.year, first_of_month.month)[1]
    return first_of_month.replace(day=1), first_of_month.replace(day=last_day)


# ─────────────────────────────────────────────────────────────
# Facts (inputs)
# ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Complaint:
    id: int
    reference: str
    plant: Optional[str]
    product_line: Optional[str]
    status: str
    opening_date: date
    due_date: Optional[datetime]
    closed_at: Optional[datetime] = None
    has_overdue_step: bool = False
    customer: Optional[str] = None
    defect: Optional[str] = None

    @property
    def counts(self) -> bool:
        return self.status not in IGNORED_COMPLAINT_STATUSES

    def late_or_overdue(self, as_of: date, lookback: tuple[date, date]) -> Optional[str]:
        """Why this complaint wasn't closed on time, or None."""
        if not self.counts:
            return None
        if self.closed_at is None:
            if self.due_date and self.due_date.date() < as_of:
                return f"open, due {self.due_date.date().isoformat()}"
            if self.has_overdue_step:
                return "open, 8D step overdue"
            return None
        if (
            self.due_date
            and self.closed_at > self.due_date
            and lookback[0] <= self.closed_at.date() <= lookback[1]
        ):
            return (
                f"closed {self.closed_at.date().isoformat()} after due "
                f"{self.due_date.date().isoformat()}"
            )
        return None

    def repeat_key(self) -> Optional[tuple]:
        values = tuple((getattr(self, f) or "").strip().lower() for f in P5_MATCH_FIELDS)
        if any(not v for v in values) or values[P5_MATCH_FIELDS.index("defect")] == "na":
            return None
        return values


def pick_next_external_audit(
    records: list[tuple[str, date]], as_of: date
) -> Optional[date]:
    """Choose the next external audit date for one plant + standard.

    records are (status, next_expected_audit) rows, status "validated" or
    "pending_review". The earliest upcoming validated date wins, then the
    earliest upcoming pending one: taking the latest date overall let a far
    pending row (Kunshan ISO 14001, 2027-02-04) hide a validated one inside
    the P10 window (2026-11-16). With nothing upcoming, the latest past date
    is returned so P8/P10 can report the record as stale.
    """
    upcoming = [(status != "validated", d) for status, d in records if d and d >= as_of]
    if upcoming:
        return min(upcoming)[1]
    past = [d for _, d in records if d]
    return max(past) if past else None


@dataclass(frozen=True)
class Project:
    code: str
    name: str
    plant: Optional[str]
    product_line: Optional[str]
    sop_date: date
    manager_name: Optional[str]
    manager_email: Optional[str]


@dataclass(frozen=True)
class Escalation:
    id: int
    plant: str
    product_line: Optional[str]
    customer: Optional[str]
    level: str  # "CSI" | "CSII"


@dataclass(frozen=True)
class MetricReading:
    plant: str
    metric: str  # nqc | scrap | ppm_internal | ppm_external
    value: float
    target: float
    source: str  # manual | mcp


@dataclass(frozen=True)
class HistoryEntry:
    plant: str
    product_line: Optional[str]
    kind: str
    support_process_id: Optional[int]
    audited_on: date


@dataclass(frozen=True)
class SupportProcess:
    id: int
    name: str


@dataclass
class Facts:
    """None for a source means "could not be read" - the checks that need it
    are reported as not evaluated instead of silently passing."""

    plan_month: date
    as_of: date
    plants: tuple[str, ...] = SCHEDULED_PLANTS
    complaints: Optional[list[Complaint]] = None
    projects: Optional[list[Project]] = None
    escalations: Optional[list[Escalation]] = None
    metrics: Optional[list[MetricReading]] = None
    history: list[HistoryEntry] = field(default_factory=list)
    support_processes: list[SupportProcess] = field(default_factory=list)
    # plant -> {"IATF16949": due date | None, "ISO14001": due date | None}
    external_audits: Optional[dict[str, dict[str, Optional[date]]]] = None
    unavailable_reasons: dict[str, str] = field(default_factory=dict)

    @property
    def lookback_month(self) -> tuple[date, date]:
        return month_bounds(add_months(self.plan_month, -1))


# ─────────────────────────────────────────────────────────────
# Candidates (outputs)
# ─────────────────────────────────────────────────────────────


@dataclass
class Candidate:
    plant: str
    product_line: Optional[str]
    merge_group: str
    history_kind: str
    trigger_codes: list[str] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    project_code: Optional[str] = None
    project_manager_name: Optional[str] = None
    project_manager_email: Optional[str] = None
    support_process_id: Optional[int] = None
    support_process_name: Optional[str] = None
    complaint_volume: int = 0
    status: Optional[str] = None
    status_reason: Optional[str] = None
    scheduled_date: Optional[date] = None

    @property
    def key(self) -> tuple:
        return (
            self.plant,
            self.product_line,
            self.merge_group,
            self.project_code,
            self.support_process_id,
        )

    @property
    def priority(self) -> int:
        return min(int(code[1:]) for code in self.trigger_codes)

    @property
    def checklist(self) -> str:
        """Audit type + what to audit, e.g. "Open Audit: Audit the 8D". Merged
        triggers (P2+P3, P4+P5) always share an audit type."""
        guides = [PRIORITY_GUIDE[code] for code in self.trigger_codes]
        scopes = list(dict.fromkeys(g["scope"] for g in guides))
        return f"{guides[0]['audit_type']}: {' + '.join(scopes)}"

    @property
    def auditee_role(self) -> str:
        return AUDITEE_ROLE[f"P{self.priority}"]


OPEN_AUDIT = "Open Audit"

# What each priority means and which audit it produces, from the audit
# priorities table. format "open" = Open Audit (the auditor types the questions),
# "checklist" = a fixed questionnaire. Shown on the planning page's guide tab.
PRIORITY_GUIDE: dict[str, dict] = {
    "P1": {
        "question": "Is there an open customer complaint (not closed on time)?",
        "rule": "A complaint still open past its due date or with an overdue 8D step, "
                "or closed last month after its due date.",
        "format": "open", "audit_type": OPEN_AUDIT, "questionnaire": "Open Audit",
        "scope": "Audit the 8D",
    },
    "P2": {
        "question": "Is there an open CSII?",
        "rule": "An open CSII escalation (entered under Manual inputs).",
        "format": "checklist", "audit_type": "Customer Complaint",
        "questionnaire": "Customer Complaint - CSI/CSII Checklist (CSL1)",
        "scope": "CSII/CSI checklist",
    },
    "P3": {
        "question": "Is there an open CSI?",
        "rule": "An open CSI escalation (entered under Manual inputs).",
        "format": "checklist", "audit_type": "Customer Complaint",
        "questionnaire": "Customer Complaint - CSI/CSII Checklist (CSL1)",
        "scope": "CSII/CSI checklist",
    },
    "P4": {
        "question": "Were there more than 3 customer complaints last month?",
        "rule": "More than 3 complaints opened last month on the same plant and product line.",
        "format": "open", "audit_type": OPEN_AUDIT, "questionnaire": "Open Audit",
        "scope": "Process owner for customer complaints - process result methodology, "
                 "VDA 6.3 input-output method",
    },
    "P5": {
        "question": "Is there a repetitive complaint in the last month?",
        "rule": "The same complaint (plant, product line, customer and defect) 2 or more "
                "times last month. Provisional rule - to be confirmed.",
        "format": "open", "audit_type": OPEN_AUDIT, "questionnaire": "Open Audit",
        "scope": "Previous 8D - root cause analysis, corrective actions implementation",
    },
    "P6": {
        "question": "Is there an SOP in the next 5 months?",
        "rule": "An APQP project not yet in production whose SOP date is within 5 months.",
        "format": "checklist", "audit_type": "Process",
        "questionnaire": "VDA 6.3 Process Audit", "scope": "VDA 6.3 P6 / P7",
    },
    "P7": {
        "question": "Was the Plant Manager audited in the last 3 months?",
        "rule": "No Plant Manager audit recorded in the last 3 months.",
        "format": "checklist", "audit_type": "Plant Manager IATF",
        "questionnaire": "Plant Manager IATF", "scope": "Plant Manager checklist",
    },
    "P8": {
        "question": "Is the external IATF audit going to happen within 4 months?",
        "rule": "Next IATF audit date within 4 months: every support process not audited "
                "internally in the last 4 months gets an audit.",
        "format": "checklist", "audit_type": "IATF Process Owner",
        "questionnaire": "IATF Process Owner Checklist",
        "scope": "IATF Process Owner checklist + external non-conformities of the last audit",
    },
    "P9": {
        "question": "Was the Recovery Plan audited in the last 3 months?",
        "rule": "No Recovery Plan audit recorded in the last 3 months.",
        "format": "open", "audit_type": OPEN_AUDIT, "questionnaire": "Open Audit",
        "scope": "Recovery Plan implementation in situ, evidences",
    },
    "P10": {
        "question": "Is the external ISO 14001 audit going to happen within 4 months?",
        "rule": "Next ISO 14001 audit date within 4 months.",
        "format": "checklist", "audit_type": "Environmental System",
        "questionnaire": "iso 14001", "scope": "ISO 14001 internal checklist",
    },
    "P11": {
        "question": "Is NQC / scrap / PPM over target?",
        "rule": "Last month's NQC or scrap (manual input) or PPM (KPI system) above target.",
        "format": "open", "audit_type": OPEN_AUDIT, "questionnaire": "Open Audit",
        "scope": "Pareto analysis + control plan + non-conforming material procedure",
    },
}


@dataclass
class Evaluation:
    candidates: list[Candidate]
    check_status: dict[str, dict]
    warnings: list[str]


class _Collector:
    def __init__(self) -> None:
        self.by_key: dict[tuple, Candidate] = {}

    def add(self, code: str, evidence: dict, **fields) -> None:
        probe = Candidate(**fields)
        cand = self.by_key.setdefault(probe.key, probe)
        if code not in cand.trigger_codes:
            cand.trigger_codes.append(code)
            cand.trigger_codes.sort(key=lambda c: int(c[1:]))
        cand.evidence.append({"check": code, **evidence})


def _audited_within(
    history: list[HistoryEntry], as_of: date, months: int, **match
) -> Optional[date]:
    """Most recent matching audit on/after as_of - months, else None."""
    since = add_months(as_of, -months)
    dates = [
        h.audited_on
        for h in history
        if h.audited_on >= since
        and h.audited_on <= as_of
        and all(getattr(h, k) == v for k, v in match.items())
    ]
    return max(dates) if dates else None


# ─────────────────────────────────────────────────────────────
# P1-P11
# ─────────────────────────────────────────────────────────────


def evaluate(facts: Facts) -> Evaluation:
    """Run all 11 checks (never stop at the first match) and return merged
    candidates. Only facts for `facts.plants` produce candidates; anything
    else is reported once in warnings."""
    out = _Collector()
    status: dict[str, dict] = {}
    warnings: list[str] = []
    plants = set(facts.plants)
    as_of = facts.as_of
    lb_start, lb_end = facts.lookback_month
    ignored_plants: set[str] = set()

    def in_scope(plant: Optional[str], source: str) -> bool:
        if plant in plants:
            return True
        ignored_plants.add(f"{plant or '(blank)'} [{source}]")
        return False

    def unavailable(codes: list[str], source: str) -> None:
        reason = facts.unavailable_reasons.get(source, f"{source} source unavailable")
        for code in codes:
            status[code] = {"status": "not_evaluated", "reason": reason}

    # ── Complaints: P1, P4, P5 ─────────────────────────────────
    if facts.complaints is None:
        unavailable(["P1", "P4", "P5"], "complaints")
    else:
        last_month: dict[tuple, list[Complaint]] = defaultdict(list)
        for c in facts.complaints:
            if not in_scope(c.plant, "complaints"):
                continue
            late = c.late_or_overdue(as_of, (lb_start, lb_end))
            if late:
                out.add(
                    "P1",
                    {"complaint": c.reference, "reason": late},
                    plant=c.plant,
                    product_line=c.product_line,
                    merge_group="8d",
                    history_kind=HISTORY_LINE,
                )
            if c.counts and lb_start <= c.opening_date <= lb_end:
                last_month[(c.plant, c.product_line)].append(c)

        for (plant, line), items in last_month.items():
            if len(items) > P4_COMPLAINT_THRESHOLD:
                out.add(
                    "P4",
                    {
                        "complaints_last_month": len(items),
                        "complaints": [c.reference for c in items],
                    },
                    plant=plant,
                    product_line=line,
                    merge_group="complaint_trend",
                    history_kind=HISTORY_LINE,
                )
            repeats: dict[tuple, list[Complaint]] = defaultdict(list)
            for c in items:
                key = c.repeat_key()
                if key:
                    repeats[key].append(c)
            for group in repeats.values():
                if len(group) >= P5_MIN_REPEATS:
                    out.add(
                        "P5",
                        {
                            "customer": group[0].customer,
                            "defect": group[0].defect,
                            "times_last_month": len(group),
                            "complaints": [c.reference for c in group],
                            "rule": "provisional",
                        },
                        plant=plant,
                        product_line=line,
                        merge_group="complaint_trend",
                        history_kind=HISTORY_LINE,
                    )
        for code in ("P1", "P4", "P5"):
            status[code] = {"status": "evaluated"}

    # ── Customer escalations: P2 (CSII), P3 (CSI) ─────────────
    if facts.escalations is None:
        unavailable(["P2", "P3"], "escalations")
    else:
        for e in facts.escalations:
            if not in_scope(e.plant, "escalations"):
                continue
            code = "P2" if e.level.upper() == "CSII" else "P3"
            out.add(
                code,
                {"level": e.level.upper(), "customer": e.customer, "escalation_id": e.id},
                plant=e.plant,
                product_line=e.product_line,
                merge_group="csi",
                history_kind=HISTORY_LINE,
            )
        status["P2"] = status["P3"] = {"status": "evaluated"}

    # ── Projects: P6 ──────────────────────────────────────────
    if facts.projects is None:
        unavailable(["P6"], "projects")
    else:
        horizon = add_months(as_of, SOP_HORIZON_MONTHS)
        for p in facts.projects:
            if not (as_of <= p.sop_date <= horizon) or not in_scope(p.plant, "projects"):
                continue
            out.add(
                "P6",
                {"project": p.code, "name": p.name, "sop_date": p.sop_date.isoformat()},
                plant=p.plant,
                product_line=p.product_line,
                merge_group="sop",
                history_kind=HISTORY_LINE,
                project_code=p.code,
                project_manager_name=p.manager_name,
                project_manager_email=p.manager_email,
            )
        status["P6"] = {"status": "evaluated"}

    # ── History-only plant checks: P7, P9 ─────────────────────
    for code, kind, months, group in (
        ("P7", HISTORY_PLANT_MANAGER, PLANT_MANAGER_WINDOW_MONTHS, "plant_manager"),
        ("P9", HISTORY_RECOVERY_PLAN, RECOVERY_PLAN_WINDOW_MONTHS, "recovery_plan"),
    ):
        for plant in facts.plants:
            if _audited_within(facts.history, as_of, months, plant=plant, kind=kind):
                continue
            out.add(
                code,
                {"reason": f"no {kind.replace('_', ' ')} audit in the last {months} months"},
                plant=plant,
                product_line=None,
                merge_group=group,
                history_kind=kind,
            )
        status[code] = {"status": "evaluated"}

    # ── External audits: P8 (IATF), P10 (ISO 14001) ──────────
    if facts.external_audits is None:
        unavailable(["P8", "P10"], "certifications")
    else:
        horizon = add_months(as_of, EXTERNAL_AUDIT_HORIZON_MONTHS)
        stale: list[str] = []
        for plant in facts.plants:
            due = facts.external_audits.get(plant, {})
            stale += [
                f"{plant} {kind} {when.isoformat()}"
                for kind, when in sorted(due.items())
                if when and when < as_of
            ]
            iatf = due.get("IATF16949")
            if iatf and as_of <= iatf <= horizon:
                if not facts.support_processes:
                    warnings.append(f"P8: IATF audit due for {plant} but no active support processes configured.")
                for sp in facts.support_processes:
                    if _audited_within(
                        facts.history,
                        as_of,
                        SUPPORT_PROCESS_WINDOW_MONTHS,
                        plant=plant,
                        kind=HISTORY_SUPPORT_PROCESS,
                        support_process_id=sp.id,
                    ):
                        continue
                    out.add(
                        "P8",
                        {"iatf_due": iatf.isoformat(), "process": sp.name},
                        plant=plant,
                        product_line=None,
                        merge_group="support_process",
                        history_kind=HISTORY_SUPPORT_PROCESS,
                        support_process_id=sp.id,
                        support_process_name=sp.name,
                    )
            iso = due.get("ISO14001")
            if iso and as_of <= iso <= horizon:
                out.add(
                    "P10",
                    {"iso14001_due": iso.isoformat()},
                    plant=plant,
                    product_line=None,
                    merge_group="iso14001",
                    history_kind=HISTORY_ISO14001,
                )
        if stale:
            warnings.append(
                "P8/P10: next external audit date is in the past (certification record "
                "not updated), so it was ignored for: " + ", ".join(stale)
            )
        status["P8"] = status["P10"] = {"status": "evaluated"}

    # ── Quality metrics: P11 ──────────────────────────────────
    if facts.metrics is None:
        unavailable(["P11"], "metrics")
    else:
        for m in facts.metrics:
            if m.value > m.target and in_scope(m.plant, "metrics"):
                out.add(
                    "P11",
                    {
                        "metric": m.metric,
                        "value": round(m.value, 4),
                        "target": m.target,
                        "source": m.source,
                    },
                    plant=m.plant,
                    product_line=None,
                    merge_group="quality_metrics",
                    history_kind=HISTORY_QUALITY_METRICS,
                )
        status["P11"] = {"status": "evaluated"}
        partial = facts.unavailable_reasons.get("metrics_partial")
        if partial:
            status["P11"] = {"status": "partial", "reason": partial}

    if ignored_plants:
        warnings.append(
            "Ignored data for plants outside the weekly schedule: "
            + ", ".join(sorted(ignored_plants))
        )

    candidates = list(out.by_key.values())
    _set_complaint_volume(candidates, facts)
    return Evaluation(candidates=candidates, check_status=status, warnings=warnings)


def _set_complaint_volume(candidates: list[Candidate], facts: Facts) -> None:
    """Complaints opened in the last 12 months, per line (or per plant for
    plant-level items) - the "top offenders" ranking used when triggers
    exceed capacity."""
    if not facts.complaints:
        return
    since = add_months(facts.as_of, -VOLUME_WINDOW_MONTHS)
    per_line: dict[tuple, int] = defaultdict(int)
    per_plant: dict[str, int] = defaultdict(int)
    for c in facts.complaints:
        if not c.counts or c.opening_date < since:
            continue
        per_line[(c.plant, c.product_line)] += 1
        per_plant[c.plant] += 1
    for cand in candidates:
        cand.complaint_volume = (
            per_line[(cand.plant, cand.product_line)]
            if cand.product_line
            else per_plant[cand.plant]
        )


# ─────────────────────────────────────────────────────────────
# Capacity rules + weekly schedule
# ─────────────────────────────────────────────────────────────


def apply_recent_line_audit_rule(
    candidates: list[Candidate], history: list[HistoryEntry], as_of: date
) -> None:
    """Don't re-audit the same line within 3 months (checked against
    completed audits, not against other items in the same run). Suppressed
    items stay in the plan so a reviewer can reinstate them."""
    for cand in candidates:
        if not cand.product_line:
            continue
        last = _audited_within(
            history,
            as_of,
            LINE_REAUDIT_WINDOW_MONTHS,
            plant=cand.plant,
            product_line=cand.product_line,
        )
        if last:
            cand.status = STATUS_SUPPRESSED_RECENT
            cand.status_reason = f"line audited on {last.isoformat()} (within 3 months)"


def schedule(
    candidates: list[Candidate],
    plan_month: date,
    *,
    holidays: Optional[dict[str, set[date]]] = None,
    not_before: Optional[date] = None,
    max_per_group_per_week: int = 1,
) -> None:
    """Assign each open candidate to its plant's fixed weekday.

    Greedy, strict priority order: candidates are ranked by check priority
    (P1 first), then complaint volume (desc, top offenders first), and each
    takes the earliest free day for its slot group that is not before any
    higher-priority audit, so a P5 is never dated ahead of a P1 whatever
    the plant or weekday (the same day is allowed). Anything that doesn't fit
    is marked over_capacity. There is no cap on audits per day: auditors are
    assigned at review time, where the 2-per-auditor-per-day cap is enforced.
    """
    holidays = holidays or {}
    week_load: dict[tuple[str, int], int] = defaultdict(int)
    first, last = month_bounds(plan_month)
    start = max(first, not_before) if not_before else first

    open_cands = [c for c in candidates if c.status is None]
    open_cands.sort(key=lambda c: (c.priority, -c.complaint_volume, c.plant, c.product_line or ""))

    # Latest date taken by an already-processed (higher) priority level, and
    # the latest date taken so far within the current level.
    floor = start
    level, level_latest = None, start

    for cand in open_cands:
        if cand.priority != level:
            floor = max(floor, level_latest)
            level, level_latest = cand.priority, floor
        group = PLANT_GROUP[cand.plant]
        weekday = SCHEDULE_GROUPS[group][0]
        d = floor + timedelta(days=(weekday - floor.weekday()) % 7)
        while d <= last:
            week = d.isocalendar()[1]
            if (
                d not in holidays.get(cand.plant, set())
                and week_load[(group, week)] < max_per_group_per_week
            ):
                cand.status = STATUS_SCHEDULED
                cand.scheduled_date = d
                week_load[(group, week)] += 1
                level_latest = max(level_latest, d)
                break
            d += timedelta(days=7)
        else:
            cand.status = STATUS_OVER_CAPACITY
            cand.status_reason = "no free weekly slot left this month"
