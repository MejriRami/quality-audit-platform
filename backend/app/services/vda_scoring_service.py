from typing import Any, Dict, List, Optional
import math


VALID_VDA_SCORES = {0, 4, 6, 8, 10}
VDA_ELEMENTS = ["P2", "P3", "P4", "P5", "P6", "P7"]
P6_SUBGROUPS = ["6.1", "6.2", "6.3", "6.4", "6.5", "6.6"]


def _round1(n: float) -> float:
    return round(n, 1)


def _floor1(n: float) -> float:
    return math.floor(n * 10) / 10


def _floor0(n: float) -> int:
    return math.floor(n)


def _rating_from_eg(eg: float) -> str:
    if eg >= 90:
        return "A"
    if eg >= 80:
        return "B"
    return "C"


def _clamp_rating(current: str, max_allowed: str) -> str:
    rank = {"A": 3, "B": 2, "C": 1}
    return max_allowed if rank[current] > rank[max_allowed] else current


def _answer_question_id(answer: Any) -> Optional[int]:
    qid = getattr(answer, "question_id", None)
    try:
        qid = int(qid)
    except (TypeError, ValueError):
        return None
    return qid if qid > 0 else None


def _answer_value(answer: Any) -> Any:
    return getattr(answer, "value", None)


def _is_answer_selected_for_scoring(answer: Any) -> bool:
    qid = _answer_question_id(answer)
    raw_value = _answer_value(answer)
    return qid is not None and raw_value in VALID_VDA_SCORES


def _normalize_element(question: Any, question_code: str) -> str:
    element = getattr(question, "element", None) or getattr(question, "chapter", None) or ""
    if element:
        return str(element).strip().upper()
    if question_code.upper().startswith("P"):
        return question_code.split(".")[0].upper()
    return "OTHER"


def _normalize_subgroup(question: Any, question_code: str) -> str:
    subgroup = getattr(question, "subgroup", None) or ""
    if subgroup:
        return str(subgroup).strip()
    if question_code.upper().startswith("P6."):
        parts = question_code.upper().split(".")
        if len(parts) >= 2 and parts[1].isdigit():
            return f"6.{parts[1]}"
    return ""


def _is_asterisk(question: Any) -> bool:
    return bool(
        getattr(question, "is_asterisk", False)
        or str(getattr(question, "question_code", "") or "").strip().endswith("*")
        or str(getattr(question, "description", "") or "").lstrip().startswith("*")
    )


def _bucket_percent(answered_rows: List[dict], total_questions_in_scope: int) -> Optional[float]:
    if not answered_rows or total_questions_in_scope == 0:
        return None

    min_required = math.ceil((2 * total_questions_in_scope) / 3)
    if len(answered_rows) < min_required:
        return None

    achieved = sum(r["score"] for r in answered_rows)
    maximum = total_questions_in_scope * 10
    return _round1((achieved / maximum) * 100) if maximum else None


def _base_question_code(question_code: str) -> str:
    code = (question_code or "").strip().upper().rstrip("*")
    parts = code.split(".")
    return ".".join(parts[:2]) if len(parts) >= 2 else code


def _normalize_process_type(answer: Any, element: str) -> str:
    if (element or "").upper() not in {"P3", "P4"}:
        return ""

    raw = str(getattr(answer, "process", "") or "").strip().lower()
    if "product" in raw:
        return "product"
    if "support" in raw or "process" in raw:
        return "process_support"
    return ""


def _requirement_score(answer: Any) -> Optional[int]:
    """A question scores its worst-met requirement (VDA 6.3).

    Averaging let one deviation disappear among fully met requirements
    (e.g. one 4 among twenty-four 10s rounded back up to 10)."""
    requirements = getattr(answer, "requirements", None) or []
    scores: List[int] = []
    for req in requirements:
        raw = getattr(req, "value", None)
        try:
            val = int(raw)
        except (TypeError, ValueError):
            continue
        if val in VALID_VDA_SCORES:
            scores.append(val)
    if not scores:
        return None
    return min(scores)


def compute_vda_results(
    answers: List[Any],
    questions_by_id: Dict[int, Any],
) -> Dict[str, Any]:
    rows: List[dict] = []
    downgrade_reasons: List[dict] = []
    critical_findings: List[dict] = []

    selected_question_ids = {
        _answer_question_id(ans)
        for ans in answers
        if _is_answer_selected_for_scoring(ans)
    }
    selected_question_ids.discard(None)

    for ans in answers:
        qid = _answer_question_id(ans)
        raw_value = _answer_value(ans)

        if qid is None or raw_value not in VALID_VDA_SCORES:
            continue

        q = questions_by_id.get(qid)
        if not q:
            continue

        question_code = (
            getattr(q, "question_code", None)
            or getattr(q, "standard_paragraph", None)
            or f"Q{qid}"
        )

        element = _normalize_element(q, question_code)
        subgroup = _normalize_subgroup(q, question_code)
        req_score = _requirement_score(ans)
        score = req_score if req_score is not None else int(raw_value)
        is_asterisk = _is_asterisk(q)

        if is_asterisk and score == 0:
            downgrade_reasons.append({
                "type": "ASTERISK_0",
                "question_id": qid,
                "question_code": question_code,
                "value": 0,
                "message": "Asterisk question scored 0: final rating forced to C.",
            })
            critical_findings.append({
                "question_id": qid,
                "question_code": question_code,
                "value": 0,
                "rule": "0_forces_C",
            })

        elif is_asterisk and score == 4:
            downgrade_reasons.append({
                "type": "ASTERISK_4",
                "question_id": qid,
                "question_code": question_code,
                "value": 4,
                "message": "Asterisk question scored 4: final rating cannot be A.",
            })
            critical_findings.append({
                "question_id": qid,
                "question_code": question_code,
                "value": 4,
                "rule": "4_blocks_A",
            })

        rows.append({
            "question_id": qid,
            "question_code": question_code,
            "question_text": (
                getattr(q, "description", None)
                or getattr(q, "question_text_en", None)
                or f"Question {qid}"
            ),
            "element": element,
            "subgroup": subgroup,
            "process_type": _normalize_process_type(ans, element),
            "score": score,
            "is_asterisk": is_asterisk,
            "finding_text": getattr(ans, "finding_text", "") or "",
        })

    # For P3/P4, merge Product+Process by base question:
    # - both answered => average
    # - one answered => use answered value
    # - 2/3 coverage counts question answered when at least one side is answered
    by_element_answered: Dict[str, List[dict]] = {el: [] for el in VDA_ELEMENTS}
    grouped_p3_p4: Dict[tuple[str, str], List[dict]] = {}

    for row in rows:
        el = row["element"]
        if el in {"P3", "P4"}:
            key = (el, _base_question_code(row.get("question_code", "")))
            grouped_p3_p4.setdefault(key, []).append(row)
            continue
        by_element_answered.setdefault(el, []).append(row)

    for (el, base_code), pair_rows in grouped_p3_p4.items():
        scores = [int(r["score"]) for r in pair_rows]
        merged_score = int(round(sum(scores) / len(scores))) if scores else 0
        ref = pair_rows[0]
        by_element_answered.setdefault(el, []).append({
            "question_id": ref.get("question_id"),
            "question_code": base_code or ref.get("question_code"),
            "question_text": ref.get("question_text"),
            "element": el,
            "subgroup": ref.get("subgroup", ""),
            "process_type": "merged_product_process",
            "score": merged_score,
            "is_asterisk": any(bool(r.get("is_asterisk")) for r in pair_rows),
            "finding_text": " | ".join(
                ft for ft in [r.get("finding_text", "") for r in pair_rows] if ft
            ),
            "merged_from_process_types": [r.get("process_type", "") for r in pair_rows],
        })

    by_element_total: Dict[str, int] = {el: 0 for el in VDA_ELEMENTS}
    grouped_total_p3_p4: Dict[str, set[str]] = {"P3": set(), "P4": set()}

    for qid in selected_question_ids:
        q = questions_by_id.get(qid)
        if not q:
            continue

        qc = getattr(q, "question_code", None) or getattr(q, "standard_paragraph", None) or ""
        el = _normalize_element(q, qc)

        if el in {"P3", "P4"}:
            grouped_total_p3_p4[el].add(_base_question_code(qc))
        elif el in by_element_total:
            by_element_total[el] += 1

    by_element_total["P3"] = len([c for c in grouped_total_p3_p4["P3"] if c])
    by_element_total["P4"] = len([c for c in grouped_total_p3_p4["P4"] if c])

    p6_rows = by_element_answered.get("P6", [])
    p6_sub: Dict[str, dict] = {}

    for sg in P6_SUBGROUPS:
        sg_answered = [r for r in p6_rows if r["subgroup"] == sg]

        sg_total = sum(
            1
            for qid in selected_question_ids
            for q in [questions_by_id.get(qid)]
            if q is not None
            if _normalize_element(
                q,
                getattr(q, "question_code", "") or getattr(q, "standard_paragraph", "") or "",
            ) == "P6"
            and _normalize_subgroup(
                q,
                getattr(q, "question_code", "") or getattr(q, "standard_paragraph", "") or "",
            ) == sg
        )

        pct = _bucket_percent(sg_answered, sg_total) if sg_total else None

        p6_sub[sg] = {
            "achieved_points": sum(r["score"] for r in sg_answered),
            "max_points": sg_total * 10,
            "eg_percent": pct,
            "answered": len(sg_answered),
            "total": sg_total,
            "min_required_23": math.ceil((2 * sg_total) / 3) if sg_total else 0,
            "rule_23_met": True if sg_total == 0 else pct is not None,
        }

    def element_percent(element: str) -> Optional[float]:
        return _bucket_percent(
            by_element_answered.get(element, []),
            by_element_total.get(element, 0),
        )

    p6_achieved = sum(r["score"] for r in p6_rows)
    p6_max = by_element_total.get("P6", 0) * 10

    ep_percent: Dict[str, Optional[float]] = {
        "P2": element_percent("P2"),
        "P3": element_percent("P3"),
        "P4": element_percent("P4"),
        "P5": element_percent("P5"),
        "P6": _round1((p6_achieved / p6_max) * 100) if p6_max else None,
        "P7": element_percent("P7"),
    }

    # FIXED TOTAL SCORE:
    # Total score = scored points / maximum possible points * 100
    all_merged_rows = [row for el_rows in by_element_answered.values() for row in el_rows]
    achieved_total = sum(r["score"] for r in all_merged_rows)
    max_points = sum(by_element_total.get(el, 0) for el in VDA_ELEMENTS) * 10

    eg_percent = _floor1((achieved_total / max_points) * 100) if max_points else 0.0
    display_score = _floor0(eg_percent)

    initial_rating = _rating_from_eg(eg_percent)
    final_rating = initial_rating

    # Section minimum thresholds (aligned with xlsx rule):
    # If any section EG% < 70 => C; if any section EG% < 80 => max B.
    available_ep = [v for v in ep_percent.values() if v is not None]
    if available_ep:
        min_ep = min(available_ep)
        if min_ep < 70:
            final_rating = "C"
        elif min_ep < 80:
            final_rating = _clamp_rating(final_rating, "B")

    if any(r["type"] == "ASTERISK_0" for r in downgrade_reasons):
        final_rating = "C"
    elif any(r["type"] == "ASTERISK_4" for r in downgrade_reasons):
        final_rating = _clamp_rating(final_rating, "B")

    elements = []

    for el in VDA_ELEMENTS:
        el_rows = by_element_answered.get(el, [])
        total_in_el = by_element_total.get(el, 0)
        pct = ep_percent.get(el)

        elements.append({
            "element": el,
            "achieved_points": sum(r["score"] for r in el_rows),
            "max_points": total_in_el * 10,
            "eg_percent": pct,
            "display_score": _floor0(pct) if pct is not None else None,
            "answered": len(el_rows),
            "total": total_in_el,
            "min_required_23": math.ceil((2 * total_in_el) / 3) if total_in_el else 0,
            "rule_23_met": True if total_in_el == 0 else pct is not None,
        })

    process_type_breakdown: Dict[str, Dict[str, dict]] = {}

    for el in ["P4"]:
        process_type_breakdown[el] = {}

        for label in ["product", "process_support", ""]:
            part_rows = [
                r
                for r in by_element_answered.get(el, [])
                if r.get("process_type", "") == label
            ]

            if not part_rows and label:
                continue

            key = label or "unspecified"

            process_type_breakdown[el][key] = {
                "achieved_points": sum(r["score"] for r in part_rows),
                "answered": len(part_rows),
                "questions": [r["question_code"] for r in part_rows],
            }

    return {
        "total": {
            "achieved_points": achieved_total,
            "max_points": max_points,
            "eg_percent": eg_percent,
            "display_score": display_score,
            "initial_rating": initial_rating,
            "final_rating": final_rating,
        },
        "elements": elements,
        "ep6_subgroups": p6_sub,
        "p3_p4_process_types": process_type_breakdown,
        "downgrade_reasons": downgrade_reasons,
        "critical_findings": critical_findings,
        "low_score_findings": [
            {
                "question_code": r["question_code"],
                "question_text": r["question_text"],
                "score": r["score"],
                "finding_text": r["finding_text"],
            }
            for r in rows
            if r["score"] < 6
        ],
    }
