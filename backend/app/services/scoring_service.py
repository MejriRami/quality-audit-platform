from __future__ import annotations

from typing import Optional


# Canonical scoring/evaluation profiles
IATF_PM = "IATF_PM"
IATF_CLASSIFICATION = "IATF_CLASSIFICATION"
ISO_SYSTEM = "ISO_SYSTEM"
OPEN = "OPEN"
VDA_PROCESS = "VDA_PROCESS"
VDA_P1_POTENTIAL = "VDA_P1_POTENTIAL"
INTERNAL = "INTERNAL"
LEGACY_STANDARD = "LEGACY_STANDARD"


def _norm(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _score_weighted_formula(total_pass: int, total_improve: int, total_fail: int) -> float:
    """
    Generic weighted formula requested for internal non-PM:
    IF((P+I+F)=0,0,ROUND((100*P + 50*I)/(P+I+F),0))
    """
    answered = total_pass + total_improve + total_fail
    if answered <= 0:
        return 0.0
    score = (100.0 * total_pass + 50.0 * total_improve) / answered
    return round(score, 0)


def _score_vda_temporary(total_pass: int, total_improve: int, total_fail: int) -> float:
    """
    Temporary VDA scoring implementation (pending dedicated VDA formula validation).
    We keep the previous normalized weighted behavior:
      score_0_10 = (P*10 + I*5 + F*0)/(P+I+F)
      score_0_100 = score_0_10 * 10
    """
    answered = total_pass + total_improve + total_fail
    if answered <= 0:
        return 0.0
    score_0_10 = ((total_pass * 10.0) + (total_improve * 5.0)) / answered
    return score_0_10 * 10.0


def _score_severity_weighted_demerit(
    *,
    major_nc: int,
    minor_nc: int,
    ofi: int,
    major_weight: float = 20.0,
    minor_weight: float = 8.0,
    ofi_weight: float = 2.0,
) -> float:
    """
    Severity-weighted demerit score:
      Score = max(0, 100 - (Wmaj*Major + Wmin*Minor + Wofi*OFI))
    """
    demerit = (major_weight * major_nc) + (minor_weight * minor_nc) + (ofi_weight * ofi)
    return max(0.0, 100.0 - demerit)


def _rating_abcd(score: float) -> str:
    if score >= 80:
        return "A"
    if score >= 60:
        return "B"
    if score >= 50:
        return "C"
    return "D"


def _looks_iso(blob: str) -> bool:
    return (
        "iso14001" in blob
        or "iso 14001" in blob
        or "iso45001" in blob
        or "iso 45001" in blob
        or "iso50001" in blob
        or "iso 50001" in blob
        or "iso" in blob
    )


def resolve_scoring_profile(
    *,
    questionnaire_name: Optional[str],
    audit_type_value: Optional[str],
    framework_code: Optional[str],
    framework_label: Optional[str],
    score_calculation: Optional[str],
    is_iatf_nc_mode: bool,
) -> str:
    """
    Resolve scoring profile with precedence:
      1) explicit score_calculation (canonical key or legacy alias)
      2) runtime mode (IATF NC negative-question flow)
      3) questionnaire / audit_type / framework semantics
      4) fallback LEGACY_STANDARD
    """
    calc_raw = _norm(score_calculation)
    calc = calc_raw.replace(" ", "").replace("-", "").replace("_", "")
    qn = _norm(questionnaire_name)
    at = _norm(audit_type_value)
    fc = _norm(framework_code)
    fl = _norm(framework_label)
    blob = " ".join([qn, at, fc, fl])

    explicit_map = {
        # Canonical keys
        "iatfpm": IATF_PM,
        "iatfclassification": IATF_CLASSIFICATION,
        "isosystem": ISO_SYSTEM,
        "vdaprocess": VDA_PROCESS,
        "vdap1potential": VDA_P1_POTENTIAL,
        "internal": INTERNAL,
        "legacystandard": LEGACY_STANDARD,
        "open": OPEN,
        # Legacy keys kept for backward compatibility
        "fs1": IATF_PM,
        "fs2": IATF_PM,
        "fs3": IATF_CLASSIFICATION,
        "fs4": LEGACY_STANDARD,
        "vda": VDA_PROCESS,
        "vda63": VDA_PROCESS,
        "vdap1": VDA_P1_POTENTIAL,
        "vda6.3": VDA_PROCESS,
        "iatfnc": IATF_CLASSIFICATION,
    }
    if calc in explicit_map:
        return explicit_map[calc]
    if calc_raw in {IATF_PM, IATF_CLASSIFICATION, ISO_SYSTEM, VDA_PROCESS, VDA_P1_POTENTIAL, INTERNAL, LEGACY_STANDARD, OPEN}:
        return calc_raw

    if is_iatf_nc_mode:
        return IATF_CLASSIFICATION

    if "special process" in blob or "internal" in blob or "standard respect" in blob:
        return INTERNAL
    if "plant manager" in blob and "iatf" in blob:
        return IATF_PM
    if _looks_iso(blob):
        return ISO_SYSTEM
    if "potential" in blob and "vda" in blob:
        return VDA_P1_POTENTIAL
    if "vda" in blob or "process" in blob:
        return VDA_PROCESS
    if "iatf" in blob:
        return IATF_CLASSIFICATION
    return LEGACY_STANDARD


def calculate_audit_score(
    *,
    total_pass: int,
    total_improve: int,
    total_fail: int,
    profile_key: str,
    major_nc_count: int = 0,
    minor_nc_count: int = 0,
    ofi_count: int = 0,
) -> dict:
    """
    Return score payload in a normalized 0..100 format.

    Formula mapping:
      - IATF_PM -> weighted formula (same as INTERNAL by request)
      - INTERNAL -> weighted formula (requested)
      - IATF_CLASSIFICATION / ISO_SYSTEM -> severity-weighted demerit score
      - VDA_PROCESS -> temporary VDA fallback
      - VDA_P1_POTENTIAL -> temporary VDA fallback (final class handled separately)
      - LEGACY_STANDARD -> weighted fallback
    """
    key = profile_key or LEGACY_STANDARD

    if key in {IATF_CLASSIFICATION, ISO_SYSTEM}:
        score = _score_severity_weighted_demerit(
            major_nc=major_nc_count,
            minor_nc=minor_nc_count,
            ofi=ofi_count,
        )
    elif key in {IATF_PM, INTERNAL, LEGACY_STANDARD, OPEN}:
        score = _score_weighted_formula(total_pass, total_improve, total_fail)
    elif key in {VDA_PROCESS, VDA_P1_POTENTIAL}:
        score = _score_vda_temporary(total_pass, total_improve, total_fail)
    else:
        score = _score_weighted_formula(total_pass, total_improve, total_fail)

    score = round(_clamp(score, 0.0, 100.0), 2)
    return {
        "profile_key": key,
        "score": score,
        "rating": _rating_abcd(score),
        "traffic_color": None,
        "total_pass": total_pass,
        "total_improve": total_improve,
        "total_fail": total_fail,
        "answered": total_pass + total_improve + total_fail,
        "major_nc_count": major_nc_count,
        "minor_nc_count": minor_nc_count,
        "ofi_count": ofi_count,
    }


def infer_default_score_calculation(
    *,
    questionnaire_name: Optional[str],
    audit_type_value: Optional[str],
    framework_code: Optional[str],
    framework_label: Optional[str],
) -> str:
    """
    Auto-fill default questionnaire score_calculation using framework/type semantics.
    Returns canonical profile key for persistence.
    """
    return resolve_scoring_profile(
        questionnaire_name=questionnaire_name,
        audit_type_value=audit_type_value,
        framework_code=framework_code,
        framework_label=framework_label,
        score_calculation=None,
        is_iatf_nc_mode=False,
    )


def resolve_report_profile(
    *,
    questionnaire_name: Optional[str],
    audit_type_value: Optional[str],
    framework_code: Optional[str],
    framework_label: Optional[str],
    is_iatf_nc_mode: bool,
) -> str:
    """
    Resolve report rendering profile:
      - VDA
      - IATF_NC
      - IATF_PM
      - STANDARD
    """
    qn = _norm(questionnaire_name)
    at = _norm(audit_type_value)
    fc = _norm(framework_code)
    fl = _norm(framework_label)
    blob = " ".join([qn, at, fc, fl])

    if is_iatf_nc_mode:
        return "IATF_NC"
    if "potential" in blob and "vda" in blob:
        return "VDA_P1"
    if "vda" in blob:
        return "VDA"
    if "plant manager" in blob and "iatf" in blob:
        return "IATF_PM"
    return "STANDARD"
