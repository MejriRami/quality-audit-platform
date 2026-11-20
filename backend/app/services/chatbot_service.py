import json
import logging
import os
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, UploadFile
from openai import APIError, APITimeoutError
from sqlalchemy.orm import Session

from app.models.corrective_action import CorrectiveAction
from app.models.portal_chatbot_document import PortalChatbotDocument
from app.models.portal_chatbot_message import PortalChatbotMessage
from app.services import blob_storage_service, car_service
from app.services.ai.document_parser import DocumentParseError, extract_text
from app.services.ai.openai_client import (
    OPENAI_MAX_TOKENS,
    OPENAI_MODEL,
    OPENAI_TEMPERATURE,
    client as _client,
    create_chat_completion as _create_chat_completion,
)

logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 20
MAX_MESSAGE_LENGTH = 4000
MAX_DAILY_MESSAGES = 100
RATE_LIMIT_SECONDS = 3

# Document attachment feature (e.g. auditee uploads a customer requirement
# spec so the coach can reference it). Kept deliberately narrow: text-only
# formats, no OCR/vision, direct-injected into the prompt rather than a
# vector store — see app/services/ai/document_parser.py for what's supported.
CHATBOT_DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".txt"}
CHATBOT_DOCUMENT_MAX_SIZE = 5 * 1024 * 1024  # 5 MB
MIN_EXTRACTED_CHARS = 200  # below this, treat as image-only/empty and reject
MAX_DOCUMENT_CHARS = 12000  # ~a few pages; keeps prompt size/cost bounded
MAX_DOCUMENTS_PER_CAR = 3  # cap how many attachments get injected into context

# Statuses an auditee still needs to act on, shown first/in full detail.
STATUS_PRIORITY = {"pending": 0, "rejected": 1, "submitted": 2, "accepted": 3, "closed": 4}
MAX_DETAILED_CARS = 25

# VDA 6.3 process element structure is fixed/public (unlike a specific finding's
# clause number), so it's safe to ground the model with the real labels here
# instead of leaving it to guess or hallucinate them.
VDA_ELEMENT_LABELS = {
    "P1": "P1 - Potential Analysis",
    "P2": "P2 - Project Management",
    "P3": "P3 - Planning of product and process development",
    "P4": "P4 - Realization of product and process development",
    "P5": "P5 - Supplier Management",
    "P6": "P6 - Process Analysis Production",
    "P7": "P7 - Customer Care, Customer Satisfaction, Service",
}

# Safety cap on how many per-question checklist requirements get listed in the
# prompt. Real questionnaires have a handful of sub-requirements per question;
# this just bounds the prompt if a question is ever misconfigured with many.
MAX_CHECKLIST_REQUIREMENTS = 30


def _checklist_requirements_section(question, answer) -> str:
    """Render the internal checklist's sub-requirements for this question,
    plus whether each was marked fulfilled for this specific finding — this is
    the organization's own checklist detail (already in the DB), distinct from
    the public standard's clause text, which we still refuse to guess at."""
    if question is None or not question.requirements:
        return ""

    answer_requirements_by_req_id = {
        r.question_requirement_id: r for r in (answer.requirements if answer else [])
    }

    ordered_requirements = sorted(
        question.requirements,
        key=lambda r: (r.sort_order if r.sort_order is not None else 9999, r.id),
    )[:MAX_CHECKLIST_REQUIREMENTS]

    lines = []
    for req in ordered_requirements:
        code = f"[{req.requirement_code}] " if req.requirement_code else ""
        answer_req = answer_requirements_by_req_id.get(req.id)
        if answer_req is None:
            status = "not individually assessed for this finding"
        elif answer_req.fulfilled is True:
            status = "fulfilled"
        elif answer_req.fulfilled is False:
            status = "NOT fulfilled" + (
                f' — auditor noted: "{answer_req.finding_text}"' if answer_req.finding_text else ""
            )
        else:
            status = "assessment not recorded"
        lines.append(f"- {code}{req.description} — {status}")

    if not lines:
        return ""
    return (
        "Internal checklist requirements for this question (your organization's own "
        "checklist item breakdown, not a public standard clause — cite these by their "
        "own wording/code, never attach an IATF/ISO/VDA clause number to them):\n"
        + "\n".join(lines)
    )


# --- Future: questionnaire guideline document -------------------------------
# Questionnaire.guideline (Questionnaire.guideline_id -> documents.id) can point
# to the source checklist/guideline file the questionnaire was built from
# (observed so far: PDF, Word, and Excel). Once needed, extract and inject its
# text here similarly to the auditee-uploaded documents above. Two gaps to
# close first:
#   1. app/services/ai/document_parser.py only supports .pdf/.docx/.txt today —
#      an .xlsx guideline would need an extractor added (e.g. openpyxl) since
#      checklists are often laid out as spreadsheets, not prose.
#   2. The file lives in blob storage / SharePoint (see Document.file_url /
#      sharepoint_* fields), not as inline bytes — fetching it means an extra
#      download step (see blob_storage_service) before extract_text() runs,
#      and that result should be cached (e.g. on the Questionnaire row or a
#      side table) rather than re-fetched/re-parsed on every chat turn.
#
# def _questionnaire_guideline_text(questionnaire) -> str:
#     if questionnaire is None or questionnaire.guideline is None:
#         return ""
#     doc = questionnaire.guideline
#     content = blob_storage_service.download_bytes_sync(doc.blob_name)  # or file_url
#     try:
#         extracted = extract_text(doc.filename, content)
#     except DocumentParseError:
#         logger.warning("Could not parse questionnaire guideline document %s", doc.id)
#         return ""
#     return extracted[:MAX_DOCUMENT_CHARS]
# ------------------------------------------------------------------------------

def _authorize_portal_access(
    plant: str, email: str, access_mode: str, session_token: str, db: Session
) -> tuple[str, str, str]:
    car_service._assert_northwind_email(email)
    normalized_plant = car_service._normalize_portal_plant(plant)
    normalized_email = car_service._normalize_portal_email(email)
    normalized_mode = car_service._normalize_access_mode(access_mode)

    car_service._assert_portal_access_allowed(
        plant=normalized_plant,
        email=normalized_email,
        access_mode=normalized_mode,
        db=db,
    )
    car_service._get_valid_portal_session(
        plant=normalized_plant,
        email=normalized_email,
        access_mode=normalized_mode,
        session_token=session_token,
        db=db,
    )
    return normalized_plant, normalized_email, normalized_mode


def _resolve_focused_car(
    car_id: int, cars: list[CorrectiveAction]
) -> CorrectiveAction:
    for car in cars:
        if car.id == car_id:
            return car
    raise HTTPException(status_code=403, detail="This corrective action is not accessible from your portal session")


def _latest_rejection(car: CorrectiveAction):
    """Most recent 'rejected' review entry for this CAR, or None. A CAR can be
    rejected more than once across resubmissions; the latest is what's
    actually driving the auditee's current required rework."""
    rejections = [h for h in (car.history or []) if h.decision == "rejected"]
    if not rejections:
        return None
    return max(rejections, key=lambda h: h.reviewed_at or datetime.min)


def _review_history_section(car: CorrectiveAction) -> str:
    """Render the auditor's review decisions (accept/reject + comment) for
    this CAR, oldest first, so the coach knows this isn't a first attempt and
    can ground the conversation in what the auditor actually said was wrong —
    instead of restarting the investigation from scratch or letting the
    auditee repeat the same rejected reasoning."""
    history = sorted(
        (h for h in (car.history or []) if h.reviewed_at is not None),
        key=lambda h: h.reviewed_at,
    )
    if not history:
        return ""

    lines = []
    for h in history:
        when = h.reviewed_at.date() if h.reviewed_at else "N/A"
        decision_label = "REJECTED" if h.decision == "rejected" else "Accepted"
        comment = f' — auditor comment: "{h.comment}"' if h.comment else ""
        lines.append(f"- {when}: {decision_label}{comment}")

    return (
        "Review history for this CAR (this is a resubmission — do not treat it as a fresh "
        "investigation; ground your coaching in what the auditor actually said was insufficient, "
        "and make sure the new root cause/corrective action genuinely addresses that gap "
        "rather than repeating the same reasoning that was already rejected):\n"
        + "\n".join(lines)
    )


def _portfolio_summary(cars: list[CorrectiveAction]) -> str:
    if not cars:
        return "The auditee currently has no corrective actions on record."

    status_counts = Counter(car.status for car in cars)
    counts_line = ", ".join(f"{status}: {count}" for status, count in sorted(status_counts.items()))

    # Show the most actionable CARs (pending/rejected first, by nearest due date) in
    # full detail; large portfolios are summarized by count instead of dumped in full,
    # to keep the prompt bounded and avoid the model having to eyeball-count a huge list.
    ordered = sorted(
        cars,
        key=lambda c: (
            STATUS_PRIORITY.get(c.status, 99),
            c.due_date or date.max,
        ),
    )
    shown = ordered[:MAX_DETAILED_CARS]
    remaining = len(ordered) - len(shown)

    lines = [f"Status counts (authoritative, use these for any counting question): {counts_line}", ""]
    for car in shown:
        audit = car.audit
        finding = car.finding or (car.answer.finding_text if car.answer else None) or "N/A"
        line = (
            f"- CAR {car.identifier or car.id} (audit {audit.audit_number if audit else 'N/A'}, "
            f"status: {car.status}, due: {car.due_date or 'N/A'}): {finding[:160]}"
        )
        if car.status == "rejected":
            rejection = _latest_rejection(car)
            if rejection and rejection.comment:
                line += f' — REJECTED, auditor said: "{rejection.comment[:200]}"'
        lines.append(line)
    if remaining > 0:
        lines.append(
            f"...and {remaining} more CAR(s) not detailed here (mostly lower-priority/closed statuses); "
            "ask about a specific audit number or CAR identifier for details."
        )
    return "\n".join(lines)


# A pattern only counts as "recurring" (a possible systemic weak spot) once it
# shows up on 2+ of the auditee's own findings — a single occurrence is just
# one finding, not a pattern worth flagging.
MIN_RECURRENCE_COUNT = 2


def _portfolio_insights(cars: list[CorrectiveAction]) -> str:
    """Lightweight, data-only insights derived purely from the auditee's own
    CARs (no external KPI service, no cross-auditee comparison) — used only in
    the general (no-CAR-focused) thread to help the auditee spot their own
    recurring weak spots rather than treating every finding as unrelated."""
    if not cars:
        return ""

    today = date.today()
    open_statuses = {"pending", "rejected"}
    overdue = [c for c in cars if c.due_date and c.due_date < today and c.status in open_statuses]

    element_counts: Counter = Counter()
    framework_counts: Counter = Counter()
    for car in cars:
        question = car.answer.question if car.answer else None
        if question and question.element:
            element_counts[question.element.strip().upper()] += 1
        questionnaire = car.audit.questionnaire if car.audit else None
        framework = questionnaire.framework if questionnaire else None
        if framework:
            framework_counts[framework.label] += 1

    lines = [f"Overdue open CARs: {len(overdue)} of {len(cars)} total (authoritative count, do not estimate)."]

    recurring_elements = [
        (VDA_ELEMENT_LABELS.get(code, code), count)
        for code, count in element_counts.most_common()
        if count >= MIN_RECURRENCE_COUNT
    ]
    if recurring_elements:
        lines.append(
            "Recurring VDA process elements across the auditee's own findings (possible "
            "systemic weak spot, not a certainty — frame as an observation to explore, not a verdict): "
            + ", ".join(f"{label} ({count}x)" for label, count in recurring_elements)
        )

    if framework_counts:
        lines.append(
            "Findings by framework: "
            + ", ".join(f"{label}: {count}" for label, count in framework_counts.most_common())
        )

    return "\n".join(lines)


def _build_system_prompt(
    cars: list[CorrectiveAction],
    focused_car: CorrectiveAction | None,
    attached_documents_text: str = "",
) -> str:
    portfolio = _portfolio_summary(cars)

    prompt = f"""You are an experienced Automotive Quality Engineer and Lead Auditor, coaching an auditee inside an audit portal. Audits here may run under IATF 16949, VDA 6.3 (Potential Analysis P1, and process elements P2-P7), ISO standards, or an organization-internal checklist — always ground your guidance in whichever framework this specific audit actually uses (given below), never assume it's IATF by default. Your two goals: help the auditee genuinely understand the non-conformity and the requirement behind it, and guide them — through rigorous, evidence-based investigation — to a Corrective Action Report (CAR) that would hold up to a real audit. You never write the final answer for them; you coach them to it.

Here is the auditee's current portfolio of corrective actions:
{portfolio}
"""

    if focused_car is None:
        insights = _portfolio_insights(cars)
        if insights:
            prompt += f"""
Portfolio-level insights (data-derived from the auditee's own CARs only — no other auditee's data, no external KPI system):
{insights}

You're in the general (no specific CAR selected) conversation. In addition to answering direct questions about the portfolio, you may proactively help the auditee spot their own recurring weak spots using ONLY the insights above (e.g. a VDA element that keeps recurring, an overdue count) — always frame this as an observation to explore, never as a diagnosis, and always suggest they open the specific CAR(s) involved to investigate properly rather than trying to root-cause a pattern in the abstract here. Never invent a pattern, count, or KPI that isn't explicitly given above.
"""

    prompt += """
LANGUAGE
- Reply in the same language the auditee is writing in.
- Determine "the auditee's language" from the conversation as a whole, not just the latest message: if most of the auditee's own messages so far have been in one language, keep replying in that language even if their latest message contains a one-off word/phrase in another language (e.g. a technical term or a quoted procedure name) — don't flip the whole reply's language over a single outlier phrase.
- If the auditee's messages are genuinely split across two languages in roughly equal measure, or this is the very first message, mirror whatever language the current message is in.
- This applies only to your own reply language — never translate or alter the auditee's own quoted words when reflecting them back (e.g. in a summary of what they said).

GENERAL RULES
- If asked which CARs are pending, overdue, or related to a topic, answer directly from the portfolio above.
- Never write the final root cause, corrective action, 5-Whys text, or CAR content for the auditee to copy-paste. Always respond with guiding questions, explanations, or feedback on what they've drafted — never a ready-made answer.
- Be an efficient coach, not a bureaucratic gatekeeper: if the auditee's message already answers several of the questions below, acknowledge that and skip straight to the next open question — don't re-ask something they already told you. The goal is a correct, evidence-based CAR produced with the least friction necessary.
- "Efficient" means skipping steps the auditee already answered — it never means skipping the root-cause investigation (steps 6-8 below) itself. Before asking about corrective actions, silently check: has a real occurrence cause AND escape cause each been traced to a system/process weakness via 5-Whys in this conversation? If not, you are not at step 9 yet, no matter how the conversation has drifted — correct your own course back to the investigation rather than following the auditee's lead into corrective actions early. The auditee doesn't know this sequence and should never have to catch you skipping it.
- Ask one investigation question at a time. Briefly explain why you're asking when it isn't obvious.
- Never invent plant information — departments, owners, dates, affected parts/products, or procedures. If something is unknown, ask; don't assume.
- Keep responses concise.
- GROUNDING (strict): every fact you state about a CAR — its status, its finding, the auditor's stated reason, any rejection comment, a procedure/document code, a date — must come verbatim from the data given to you in this prompt (the portfolio above, or the "currently focused" CAR block below if one is active). If the auditee asks about a specific CAR/audit number, first check it actually matches what's described below or in the portfolio; if it doesn't match, or the detail they're asking about was never given to you, say plainly that you don't have that specific information rather than producing a plausible-sounding answer. Never carry over or reuse a fact, reason, or rejection comment from a CAR discussed earlier in this conversation when answering about a different CAR — each CAR's facts are independent, and restating the wrong CAR's data is a serious credibility failure, worse than saying "I don't have that detail."
- CROSS-CAR ISOLATION: the portfolio summary above lists MULTIPLE CARs, each with its own status/finding/rejection comment on its own line — when answering a question about "this CAR" while one is focused below, the answer must come ONLY from that focused CAR's own block, never from a different CAR's line in the portfolio summary, even if it's the most recent one mentioned, sounds similar, or belongs to the same audit. Before stating a rejection reason, finding, or any other fact "about this CAR," explicitly re-check that the fact you're about to state is attributed to the CARTHAGE CAR identifier as the one in the "currently focused corrective action" block — if you're not certain which CAR a fact belongs to, say so rather than guessing.
- If the auditee's message names a CAR/audit identifier that differs from the one described in the "currently focused corrective action" block below, treat that as the auditee possibly meaning a different CAR than the one currently focused — say so explicitly and ask them to refocus the chat on that CAR (via the CAR selector) rather than answering as if it were the focused one.
- FILE UPLOADS: you can accept a file attachment here, but only as reference material to inform THIS conversation (e.g. a customer spec) — it is stored separately and is NOT the CAR's evidence, does not count toward the form's required document(s), and is never seen by the auditor. If the auditee asks you to upload/attach their evidence for them, or seems to think attaching it here satisfies the submission requirement, correct that explicitly: they still need to attach it themselves in the "Related documents" section of the submission form before they can submit.
- STAY ON TOPIC: you are a coach for this auditee's corrective actions, audits, and the applicable standard — not a general-purpose assistant. If asked something with no real connection to their CARs, the audit process, or the standard/framework involved, decline politely and redirect back to their corrective actions rather than answering as a general chatbot would. This does not apply to legitimate portfolio-level questions (their own CARs, statuses, patterns) — only to genuinely unrelated requests.

INVESTIGATION WORKFLOW — do not jump straight to "Why?", and do not skip PAST "Why?" either. Work through this sequence, adapting to what the auditee has already told you. The auditee does not know these steps and must never be expected to — self-monitor your own position in the sequence and correct your own course; do not rely on the auditee to notice you skipped ahead and redirect you back:
1. Establish the facts first. Summarize the finding in plain language — what requirement was violated — and state whether it is a customer-specific requirement (CSR) or a requirement of the framework this audit runs under (an IATF 16949 clause, a VDA 6.3 process element, an ISO clause, or an internal checklist item) — these are different and must never be conflated. Check the auditee agrees with your understanding before moving on.
2. Classify what actually happened before asking "why". Offer this as a short multiple-choice, don't ask "why" yet: never planned / planned but not executed / executed but not documented / executed incorrectly / excluded from scope / still under investigation.
3. Gather only the facts that will actually influence the investigation (e.g. is the part/process still active, who owns it, where records should live, is this the first occurrence) — don't interrogate for its own sake.
4. Determine scope: is this isolated to one part/line, or systemic across others? This shapes containment.
5. Separate containment from corrective action. Containment = what's been done right now to protect the customer (e.g. catch up the overdue activity, quarantine, notify the customer if required). Corrective action comes later, after root cause — don't let the auditee conflate the two.
6. Investigate both the occurrence cause AND the escape cause — never stop at just one. Occurrence cause: why did the problem happen (planning gap, missing process, unclear ownership, training gap)? Escape cause: why wasn't it caught earlier (audit missed it, no KPI/monitoring, review failed, no reminder system)?
7. Run a guided 5-Whys only once you have enough facts. Each "why" must build on the auditee's own previous answer — never invent or guess their answer for them. If you lack enough information to go deeper, ask for it instead of guessing.
8. Reject weak/superficial root causes. "Human error", "forgot", "carelessness", "operator mistake" are symptoms, not root causes — push the auditee to keep going until they land on a system or process weakness.
9. Corrective actions must be SMART and distinct from containment. Differentiate clearly: Containment → Correction → Corrective Action → Preventive/Systemic Action. A corrective action should eliminate the root cause, have an owner, a due date, be measurable, and be realistic. NEVER ask "what corrective actions do you have in mind" or otherwise solicit fixes until steps 6-8 are actually done — i.e. until an occurrence cause AND an escape cause have each been traced through a real 5-Whys to a system/process-level root cause, not a surface-level statement like "nobody owns it" or "it wasn't tested." If you catch yourself about to ask for corrective actions with no such root cause on the table yet, stop and go back to step 6/7 instead — silently, in the same reply, without waiting for the auditee to point it out.
   When you critique or suggest tightened wording for the auditee's own corrective action text (never author it outright), nudge them toward audit-document convention: one imperative sentence or short phrase per action, starting with an action verb (e.g. Revise, Implement, Install, Train, Update, Add, Establish, Automate) naming the concrete change, followed by owner and due date — not a paragraph explaining reasoning or intent. E.g. "Revise the calibration SOP to require a second sign-off before release — Owner: J. Martin, due 15/09/2026," not "In order to prevent recurrence, we are planning to work with the quality team to look into revising the procedure over the coming weeks."
   Before accepting a proposed corrective action as settled, check it against these common auditor rejection triggers and push back if any apply: (a) does it actually close the root cause you just traced through the 5-Whys, or a different/more generic problem? (b) if the issue was systemic (step 4), does the action cover that full scope, or only the one occurrence? (c) is there a named piece of evidence that will verify effectiveness (a re-audit, a KPI trend, a re-qualification record), not just a due date with no way to confirm it worked? (d) is the due date an actual date, not "ongoing" or "as soon as possible"? (e) is it unconditional — no "will try to" / "where possible" / "if resources allow"? (f) is it ONE action, not several bundled into one sentence — if the auditee names multiple fixes at once, ask them to state each separately with its own owner/date/verification.
10. Close with effectiveness verification — e.g. next scheduled requalification completed on time, internal audit confirms compliance, automated reminders now in place, no recurrence after N months.
11. Once the systemic root cause (occurrence + escape), corrective actions, and effectiveness verification are all settled, explicitly guide the auditee on how to complete their CAR submission in the portal form: tell them, in their own words, to (a) write the causal chain we built as their 5-Whys entries, (b) summarize the corrective/preventive action taken as their "Implemented solution", and (c) attach at least one evidence document before submitting — the form requires 3+ Why statements and 1+ document. Ask if they feel ready to submit or want help refining the wording of what THEY drafted — you may critique or suggest improvements to their draft, but still never author the final sentences yourself.

STANDARDS — be careful here, and adapt to the actual framework of this audit
- IATF 16949 / ISO: only state a specific clause or paragraph number (e.g. "IATF 16949 8.5.1.1") if it is explicitly given to you below as the "Standard paragraph referenced". If it isn't provided, describe the expectation in plain language and explicitly tell the auditee to confirm the exact clause with their auditor — never state a clause number from memory.
- VDA 6.3: this standard is organized into Potential Analysis (P1) and process elements P2-P7, not numbered clauses. You may refer to the general topic of a process element by name if given (e.g. "this falls under P5 Supplier Management") since that structure is fixed and well known, but do not invent a specific sub-item/question number that wasn't given to you.
- Internal checklist: if the audit runs on an internal checklist (not a public standard), there is no external clause to cite at all — refer only to "your organization's internal checklist requirement" based on the finding/question text provided, never attach an IATF/ISO/VDA reference to it.
- In all cases: stating a wrong clause/element reference to an auditee is a serious credibility and compliance risk; when in doubt, do not cite one.
- Always distinguish a customer-specific requirement (CSR) from the audit framework's own requirement — don't imply a CSR comes directly from IATF/VDA/ISO just because the audit runs under that framework.

METHODOLOGY
- Default to the workflow above. If the auditee prefers Fishbone/6M, or wants to reason separately about occurrence vs. escape cause, support that and let them switch methodology.
"""

    if focused_car is not None:
        audit = focused_car.audit
        answer = focused_car.answer
        question = answer.question if answer else None
        questionnaire = audit.questionnaire if audit else None
        framework = questionnaire.framework if questionnaire else None
        audit_type = (
            questionnaire.audit_type.value
            if questionnaire and questionnaire.audit_type
            else None
        )
        standard_name = framework.label if framework else "the applicable framework"

        evidence_docs = (
            focused_car.answer.documents if focused_car.answer else []
        )
        evidence_lines = "\n".join(f"- {doc.filename}" for doc in evidence_docs) or "None uploaded yet."
        standard_paragraph = answer.standard_paragraph if answer and answer.standard_paragraph else None

        element_code = (question.element or "").strip().upper() if question and question.element else None
        element_line = VDA_ELEMENT_LABELS.get(element_code, element_code) if element_code else "Not provided"

        checklist_section = _checklist_requirements_section(question, answer)
        review_history_section = _review_history_section(focused_car)

        audit_dates = (
            f"planned {audit.planned_start_date.date()} to {audit.planned_end_date.date()}"
            if audit and audit.planned_start_date and audit.planned_end_date
            else "N/A"
        )
        if audit and audit.actual_start_date:
            audit_dates += f"; actually ran {audit.actual_start_date.date()}" + (
                f" to {audit.actual_end_date.date()}" if audit.actual_end_date else " (ongoing/unclosed)"
            )
        questionnaire_name = (
            f"{questionnaire.name} (v{questionnaire.version})" if questionnaire else "N/A"
        )

        prompt += f"""
The auditee is currently focused on this specific corrective action — CAR {focused_car.identifier or focused_car.id}. This identifier is how you confirm which CAR you're discussing; if the auditee's message refers to a different CAR identifier or a different audit number than the ones below, that is NOT this CAR — say so and ask them to refocus the chat instead of answering as if it matched.
CAR: {focused_car.identifier or focused_car.id}
Audit: {audit.audit_number if audit else "N/A"} — {audit.plant if audit else "N/A"} / {audit.sector or "N/A"}, {audit_dates}
Questionnaire used: {questionnaire_name}
Framework: {standard_name}{f" (audit type: {audit_type})" if audit_type else ""}
CAR status: {focused_car.status}
Finding / non-conformity: {answer.finding_text if answer else "N/A"}
Standard clause/paragraph referenced: {standard_paragraph or "Not provided — do not guess or state a specific clause/paragraph number for this finding."}
VDA 6.3 process element (only relevant if this is a VDA 6.3 audit): {element_line}
Questionnaire question: {question.description if question else "N/A"}
Auditor's stated reason: {focused_car.reason_why or "N/A"}
Evidence documents currently attached:
{evidence_lines}

Focus your coaching on this finding unless the auditee asks about something else in their portfolio. Use the STANDARDS rules above to decide how (or whether) to reference a specific clause/element for this framework.
"""

        if checklist_section:
            prompt += f"""
{checklist_section}
"""

        if review_history_section:
            prompt += f"""
{review_history_section}
"""

        if attached_documents_text:
            prompt += f"""
The auditee has also uploaded the following document(s) related to this corrective action (e.g. a customer requirement specification). Use this content as reference material to inform your coaching — for example, to check whether the finding/requirement lines up with what the document actually states, or to help the auditee understand a requirement it describes. This is auditee-supplied material, not verified fact: if it appears to conflict with the auditor's stated finding or reason, flag that gently rather than assuming the document is authoritative.
{attached_documents_text}
"""

    return prompt


def _attached_documents_context(car_id: int, db: Session) -> str:
    # Scoped by car_id alone, not by the uploader's own (email, access_mode):
    # a CAR can be worked by any auditee assigned to its audit (see
    # _query_auditee_portal_cars), and the caller here has already been
    # authorized against that same CAR via _resolve_focused_car. Filtering
    # further by the exact uploader identity meant a document uploaded under
    # one email/access_mode silently vanished from the prompt the moment a
    # different assigned auditee (or the same person switching access_mode)
    # continued the conversation on the same CAR.
    docs = (
        db.query(PortalChatbotDocument)
        .filter_by(car_id=car_id)
        .order_by(PortalChatbotDocument.created_at.desc())
        .limit(MAX_DOCUMENTS_PER_CAR)
        .all()
    )
    if not docs:
        return ""
    parts = []
    for doc in docs:
        note = " (truncated to first portion)" if doc.truncated else ""
        parts.append(f"--- Document: {doc.filename}{note} ---\n{doc.extracted_text}")
    return "\n\n".join(parts)


def get_chat_history(
    plant: str, email: str, access_mode: str, session_token: str, db: Session
) -> list[dict]:
    normalized_plant, normalized_email, normalized_mode = _authorize_portal_access(
        plant, email, access_mode, session_token, db
    )
    messages = (
        db.query(PortalChatbotMessage)
        .filter_by(plant=normalized_plant, email=normalized_email, access_mode=normalized_mode)
        # `id` as a secondary key guarantees a deterministic order even if two
        # rows ever share the same created_at (see send_message) — ORDER BY on
        # a non-unique key alone has no defined tiebreak.
        .order_by(PortalChatbotMessage.created_at, PortalChatbotMessage.id)
        .all()
    )
    return [
        {"role": m.role, "content": m.content, "car_id": m.car_id, "created_at": m.created_at}
        for m in messages
    ]


def _enforce_rate_limits(identity_filter: dict, db: Session) -> None:
    """Shared abuse guard for any endpoint that triggers an OpenAI call for a
    portal identity (conversational messages and one-off draft generation
    alike): a short cooldown between calls, plus a rolling 24h cap."""
    now = datetime.now(timezone.utc)

    last_message = (
        db.query(PortalChatbotMessage)
        .filter_by(**identity_filter)
        .order_by(PortalChatbotMessage.created_at.desc(), PortalChatbotMessage.id.desc())
        .first()
    )
    if last_message and last_message.created_at:
        elapsed = (now - last_message.created_at).total_seconds()
        if elapsed < RATE_LIMIT_SECONDS:
            raise HTTPException(
                status_code=429,
                detail="You're sending messages too quickly, please wait a moment.",
            )

    daily_count = (
        db.query(PortalChatbotMessage)
        .filter_by(**identity_filter)
        .filter(PortalChatbotMessage.created_at >= now - timedelta(hours=24))
        .count()
    )
    if daily_count >= MAX_DAILY_MESSAGES:
        raise HTTPException(
            status_code=429,
            detail="Daily chat message limit reached, please try again tomorrow.",
        )


def send_message(
    plant: str,
    email: str,
    access_mode: str,
    session_token: str,
    db: Session,
    message: str,
    car_id: int | None = None,
) -> dict:
    if not _client:
        raise HTTPException(status_code=503, detail="Chatbot is not configured")

    message = (message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    if len(message) > MAX_MESSAGE_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Message is too long (max {MAX_MESSAGE_LENGTH} characters)",
        )

    normalized_plant, normalized_email, normalized_mode = _authorize_portal_access(
        plant, email, access_mode, session_token, db
    )

    cars = car_service._query_auditee_portal_cars(
        normalized_plant, normalized_email, normalized_mode, db
    )

    focused_car = _resolve_focused_car(car_id, cars) if car_id is not None else None

    identity_filter = {"plant": normalized_plant, "email": normalized_email, "access_mode": normalized_mode}
    _enforce_rate_limits(identity_filter, db)

    # Scoped to the same conversation thread the reply will join: the focused
    # CAR's own history, or the general (no-CAR) thread when browsing the
    # portfolio. Without this filter, switching between CARs mixes unrelated
    # findings' Q&A into the model's context — confusing the 5-Whys thread and
    # wasting the history window on irrelevant turns.
    history = (
        db.query(PortalChatbotMessage)
        .filter_by(**identity_filter, car_id=focused_car.id if focused_car else None)
        .order_by(PortalChatbotMessage.created_at, PortalChatbotMessage.id)
        .all()
    )

    attached_documents_text = (
        _attached_documents_context(focused_car.id, db) if focused_car else ""
    )
    chat_messages = [
        {"role": "system", "content": _build_system_prompt(cars, focused_car, attached_documents_text)}
    ]
    chat_messages += [
        {"role": m.role, "content": m.content} for m in history[-MAX_HISTORY_MESSAGES:]
    ]
    chat_messages.append({"role": "user", "content": message})

    request_kwargs = {
        "model": OPENAI_MODEL,
        "messages": chat_messages,
        "max_completion_tokens": OPENAI_MAX_TOKENS,
        "temperature": OPENAI_TEMPERATURE,
    }

    try:
        completion = _create_chat_completion(request_kwargs)
        reply = completion.choices[0].message.content
    except APITimeoutError:
        logger.error("OpenAI request timed out for portal identity %s/%s", normalized_plant, normalized_email)
        raise HTTPException(status_code=504, detail="Chatbot timed out, please try again")
    except APIError:
        logger.exception("OpenAI request failed for portal identity %s/%s", normalized_plant, normalized_email)
        raise HTTPException(status_code=502, detail="Chatbot is temporarily unavailable")

    # The assistant reply must sort strictly after the user message that
    # triggered it. Giving both rows the exact same `now` (as this used to
    # do) makes their relative order undefined once re-queried from the DB —
    # ORDER BY created_at has no tiebreaker for equal timestamps, so a fresh
    # page load can render the pair swapped/interleaved even though the live
    # session (built from local state, not a re-query) looked fine. A single
    # microsecond bump is enough to make the pair's order deterministic.
    now = datetime.now(timezone.utc)
    db.add(PortalChatbotMessage(
        plant=normalized_plant, email=normalized_email, access_mode=normalized_mode,
        car_id=focused_car.id if focused_car else None, role="user", content=message, created_at=now,
    ))
    db.add(PortalChatbotMessage(
        plant=normalized_plant, email=normalized_email, access_mode=normalized_mode,
        car_id=focused_car.id if focused_car else None, role="assistant", content=reply,
        created_at=now + timedelta(microseconds=1),
    ))
    db.commit()

    return {"reply": reply}


MIN_MESSAGES_FOR_DRAFT = 4

# Structured-output schema for generate_draft's response. Using the API's
# native JSON schema mode (rather than a "respond with STRICT JSON ONLY"
# prompt instruction + manual fence-stripping) guarantees the shape at the API
# level instead of hoping the model complies — no markdown-fence parsing, no
# guessing whether a field is missing. create_chat_completion() already drops
# unsupported request params and retries (see openai_client.py), so this still
# degrades gracefully if a future model doesn't support response_format.
_DRAFT_ENTRY_SCHEMA = {
    "type": "object",
    "properties": {
        # "text" is always English — the official record language, since CARs
        # here can be reviewed by non-native-language auditors/customers.
        "text": {"type": "string"},
        # "text_native" preserves the auditee's own words in whatever language
        # the conversation actually used, so they can verify the English
        # version is a faithful translation before submitting. Null when the
        # conversation was already conducted in English (nothing to duplicate).
        "text_native": {"type": ["string", "null"]},
        "verdict": {"type": "string", "enum": ["ready", "weak"]},
        "suggested_rewrite": {"type": ["string", "null"]},
        # Distinct from suggested_rewrite: only used when "text" is empty (nothing
        # discussed yet at all), to give the auditee a hypothetical illustration to
        # react to/edit rather than a blank field + guiding question alone. Never
        # grounded in the auditee's own words (there are none yet) — must be
        # unmistakably labeled as an example, never presented as fact.
        "example_suggestion": {"type": ["string", "null"]},
        "note": {"type": ["string", "null"]},
    },
    "required": ["text", "text_native", "verdict", "suggested_rewrite", "example_suggestion", "note"],
    "additionalProperties": False,
}

DRAFT_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "car_draft",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "whys": {
                    "type": "array",
                    "items": _DRAFT_ENTRY_SCHEMA,
                    "maxItems": 5,
                },
                "implemented_solution": _DRAFT_ENTRY_SCHEMA,
                "overall_ready": {"type": "boolean"},
            },
            "required": ["whys", "implemented_solution", "overall_ready"],
            "additionalProperties": False,
        },
    },
}


def _build_draft_prompt(car: CorrectiveAction, transcript: str) -> str:
    return f"""You are helping an auditee turn a coaching conversation about corrective action CAR {car.identifier or car.id} into a draft submission.

Below is the full conversation between the auditee and their coaching assistant about this finding:
---
{transcript}
---

Task: extract what the AUDITEE THEMSELVES said in that conversation into a draft. Do not invent, assume, or add any fact, owner, date, or claim that the auditee did not actually state above — every "text"/"text_native" field must be a faithful reflection of their own words, not new content.

Read the ENTIRE conversation from start to end before extracting anything — do not stop scanning after the first hedging or symptom-level answer ("I don't know, it's just how it is", "human error", etc.). The auditee may resume or deepen the investigation later in the same conversation, even after the assistant seemed to close a line of questioning; a genuine "why N" answer can appear anywhere in the transcript, not only in the turn immediately following the corresponding "why N" question. Build the causal chain from ALL substantive causal statements the auditee made, in the order the underlying reasoning progresses (occurrence cause chain, then escape cause if discussed) — never truncate the chain early just because an earlier answer looked like a dead end if the conversation continues past it with more substance.

RESUBMISSION AWARENESS: this transcript may span more than one submission cycle — e.g. the CAR was submitted, an auditor rejected it (the conversation may reference "the auditor rejected this" or similar), and the auditee is now discussing what's been fixed before resubmitting. When this happens:
- The root cause (the whys) usually does NOT change across rounds — keep extracting the same causal chain, don't re-derive it from the later round alone.
- The IMPLEMENTED SOLUTION very much CAN and SHOULD change: a later statement describing an action as actually DONE/completed/verified (e.g. "we re-ran the test on 21/08 and confirmed recovery", "the plan now names X as owner") supersedes an earlier statement describing the same action as merely PLANNED/committed (e.g. "we will update the procedure, target completion in 4 weeks"). Always extract the auditee's MOST CURRENT stated status for the implemented solution, not the first solution-shaped statement you find in the transcript — a later "this is done, here's the evidence" must overwrite an earlier "here's what we plan to do," never sit alongside it as if both were still open commitments.
- Do not re-ask (via "note") a question the auditee already answered later in the same transcript — scan forward for their answer before flagging something as still missing.

LANGUAGE: the conversation may have been conducted in any language. For every entry:
- "text_native": the auditee's own words, in whatever language they actually used, unmodified in substance — this is what they can check to confirm nothing was lost or altered. If the conversation was already entirely in English, set "text_native" to null (nothing to duplicate).
- "text": the CARTHAGE content translated faithfully into English — this is the official record language for the CAR. Never add, drop, or soften a fact in translation; if a word/phrase is ambiguous, translate it as literally as possible rather than guessing intent.
- "suggested_rewrite" and "note" (see below) are always in English, regardless of the conversation's language.

The conversation may contain turns that are NOT part of the causal investigation — e.g. the auditee asking a question back to the assistant, clarifying which finding they mean, discussing an uploaded reference document, or asking about an unrelated standard/clause. Do not turn these into "why" entries. A valid "why" entry must be a substantive causal statement the auditee made about why the nonconformity occurred or escaped detection — never a question they asked, a meta-comment about which topic they're addressing, or a request for information. If the substantive causal answers found in the conversation are fewer than 5, return only that many real entries — do not pad the list with non-causal content just to reach 5. However, if the 5-Whys chain is clearly unfinished (the last real why is still a symptom or hasn't reached a systemic cause) and there's enough context from the finding and the whys already given to illustrate a plausible next step, you MAY append exactly one additional why entry with "text"/"text_native" left empty and "example_suggestion" populated per the rule below, so the auditee sees where the chain could go next — never more than one such entry, and never in place of a real entry the auditee actually gave. If the auditee has not yet described an implemented solution, set implemented_solution.text (and text_native) to an empty string rather than inventing one.

Then, act as an expert IATF/VDA 6.3 lead auditor and JUDGE each entry (each why, and the implemented_solution) for whether it is genuinely audit-ready — judge the substance, independent of which language it was originally expressed in:
- "ready" = a real systemic/process root cause — never "human error", "forgot", "carelessness", or similar symptom-level statements — OR, for the implemented solution, a SMART corrective/preventive action distinct from mere containment, with an owner, a due date, and a measurable/verifiable outcome.
- "weak" = a symptom rather than a root cause, a vague or unmeasurable action, or missing key elements (owner, date, verification), OR an empty/not-yet-discussed entry.

Additional checks specifically for the implemented_solution entry — any one of these also makes the verdict "weak" even if it otherwise looks SMART:
- TRACEABILITY: the action must actually close the root cause established in the last why of the chain above, not a different or more generic problem. If it doesn't clearly trace back to that root cause, it's "weak" — note should say so explicitly (e.g. "this addresses X, but the root cause you identified was Y — how does this action close that gap?").
- SYSTEMIC SCOPE: if the investigation concluded the issue is systemic (not isolated to one part/line/shift — see the scope discussion earlier in the transcript, if any), the action must address that same scope. An action that only fixes the one occurrence when the auditee themselves described it as systemic is "weak".
- VERIFICATION METHOD: "measurable/verifiable outcome" means a named piece of objective evidence (e.g. "next requalification audit on 15/09 confirms compliance", "PPAP re-approval", "zero recurrence in the next 3 monthly KPI reviews") — a due date alone, with no stated verification method, is still "weak".
- CONCRETE DUE DATE: open-ended or rolling timeframes ("ongoing", "by end of year", "as soon as possible") don't count as a due date — "weak" until the auditee gives an actual date.
- NO HEDGING: language like "will try to", "where possible", "as needed", "if resources allow" undermines auditability regardless of the other criteria — treat as "weak" and note that the commitment needs to be unconditional.
- ONE ACTION PER STATEMENT: if the auditee bundled multiple distinct actions into one statement (e.g. "update the SOP and retrain everyone and add a checklist"), that's still "weak" even if each piece individually looks SMART — the note should ask them to split it into separate actions, each with its own owner/date/verification, since a mixed bundle can't be tracked or closed as one item.

WORDING STYLE for "suggested_rewrite" and "example_suggestion" on the implemented_solution entry (this does NOT apply to "text"/"text_native", which must stay a faithful reflection of the auditee's own words even if rambling): write it as one imperative sentence or short phrase, not a paragraph — start with an action verb naming the concrete change (e.g. Revise, Implement, Install, Train, Update, Add, Establish, Automate), then owner, then due date. E.g. "Revise the calibration SOP to require a second sign-off before release — Owner: J. Martin, due 15/09/2026." Never a narrative like "In order to prevent this from happening again, the team plans to work on reviewing and eventually updating the procedure."

For every entry:
- If verdict is "weak": you may still set "suggested_rewrite" to a tightened version, but ONLY by reorganizing/clarifying facts the auditee already stated somewhere in the conversation above — never invent a root cause, owner, date, or action the auditee never said, and never upgrade a symptom ("human error", "forgot") into a system-level cause on their behalf. If the conversation does not yet contain enough substance to reorganize into something meaningfully better than what's in "text" (e.g. the entry is empty, or is purely a symptom with nothing systemic said yet), set "suggested_rewrite" to null instead of padding it with generic audit boilerplate. Always set "note" to a short guiding question (in English) pointing at what's still missing or unverified — even when a suggested_rewrite is present, the entry is still "weak" and the note must make clear it still needs the auditee's own further investigation before it's audit-ready.
- If verdict is "ready" but the wording could be tightened for clarity/precision as a formal audit document WITHOUT adding any new fact, changing its substance, or inventing an owner/date/detail not stated by the auditee: set "suggested_rewrite" to the improved English wording, and "note" to null. If the original wording is already clear and formal enough, set "suggested_rewrite" to null too.
- "example_suggestion" is separate from "suggested_rewrite" and only applies when "text" is empty (i.e. the auditee hasn't actually said anything substantive here yet — an unreached why, or a not-yet-discussed implemented_solution): set it to ONE plausible, hypothetical illustration of what a genuinely strong entry could look like for THIS specific finding/framework/element (grounded in the finding, standard, and whatever occurrence/escape-cause reasoning the auditee already gave for earlier whys — not a generic template), so the auditee has something concrete to react to, correct, or reject. Prefix it with "Example (not based on your investigation — adapt or replace with your own facts): " so it can never be mistaken for something the auditee said or a verified fact. Do not set it for entries that already have real "text" content — that's what suggested_rewrite is for. Always leave "note" set alongside it, making clear this is a hypothetical starting point, not a conclusion, and that the underlying investigation (owner, date, verification, actual cause) is still the auditee's to do.

Finally set "overall_ready" to true only if every why entry is "ready" AND the implemented_solution is "ready"; otherwise false. An entry whose only content is an "example_suggestion" (i.e. "text" is still empty) must never count as "ready".

Respond with STRICT JSON ONLY, no markdown code fences, no commentary, in exactly this shape:
{{
  "whys": [
    {{"text": "...English translation...", "text_native": "...auditee's own words in their original language, or null if already English...", "verdict": "ready" | "weak", "suggested_rewrite": "...or null...", "example_suggestion": "...or null...", "note": "...or null..."}}
  ],
  "implemented_solution": {{"text": "...English translation, or empty string...", "text_native": "...original language, or null...", "verdict": "ready" | "weak", "suggested_rewrite": "...or null...", "example_suggestion": "...or null...", "note": "...or null..."}},
  "overall_ready": true | false
}}
"""


def generate_draft(
    plant: str,
    email: str,
    access_mode: str,
    session_token: str,
    db: Session,
    car_id: int,
) -> dict:
    if not _client:
        raise HTTPException(status_code=503, detail="Chatbot is not configured")

    normalized_plant, normalized_email, normalized_mode = _authorize_portal_access(
        plant, email, access_mode, session_token, db
    )

    cars = car_service._query_auditee_portal_cars(
        normalized_plant, normalized_email, normalized_mode, db
    )
    focused_car = _resolve_focused_car(car_id, cars)

    identity_filter = {"plant": normalized_plant, "email": normalized_email, "access_mode": normalized_mode}
    _enforce_rate_limits(identity_filter, db)

    car_messages = (
        db.query(PortalChatbotMessage)
        .filter_by(**identity_filter, car_id=focused_car.id)
        .order_by(PortalChatbotMessage.created_at, PortalChatbotMessage.id)
        .all()
    )
    if len(car_messages) < MIN_MESSAGES_FOR_DRAFT:
        raise HTTPException(
            status_code=400,
            detail="Not enough conversation yet to generate a draft — keep discussing the investigation first.",
        )

    transcript = "\n".join(f"{m.role}: {m.content}" for m in car_messages)
    draft_prompt = _build_draft_prompt(focused_car, transcript)

    request_kwargs = {
        "model": OPENAI_MODEL,
        "messages": [{"role": "system", "content": draft_prompt}],
        "max_completion_tokens": OPENAI_MAX_TOKENS,
        "temperature": OPENAI_TEMPERATURE,
        "response_format": DRAFT_RESPONSE_FORMAT,
    }

    try:
        completion = _create_chat_completion(request_kwargs)
        raw_reply = completion.choices[0].message.content or ""
    except APITimeoutError:
        logger.error("OpenAI draft request timed out for CAR %s", focused_car.id)
        raise HTTPException(status_code=504, detail="Chatbot timed out, please try again")
    except APIError:
        logger.exception("OpenAI draft request failed for CAR %s", focused_car.id)
        raise HTTPException(status_code=502, detail="Chatbot is temporarily unavailable")

    if not raw_reply.strip():
        logger.error("Empty draft response from model for CAR %s", focused_car.id)
        raise HTTPException(status_code=502, detail="Could not generate a draft, please try again.")

    # response_format should already guarantee valid JSON with no fences; this
    # stripping is a defensive fallback for the rare case create_chat_completion
    # had to drop response_format because the configured model doesn't support it
    # (see openai_client.py's unsupported-parameter retry), where the prompt's
    # "STRICT JSON ONLY" instruction is the only thing keeping output well-formed.
    cleaned = raw_reply.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]

    def _normalize_entry(raw: object) -> dict:
        if not isinstance(raw, dict):
            return {
                "text": str(raw), "text_native": None, "verdict": "weak",
                "suggested_rewrite": None, "example_suggestion": None, "note": None,
            }
        verdict = raw.get("verdict") if raw.get("verdict") in ("ready", "weak") else "weak"
        text = str(raw.get("text", ""))
        text_native = raw.get("text_native")
        suggested_rewrite = raw.get("suggested_rewrite")
        example_suggestion = raw.get("example_suggestion")
        note = raw.get("note")
        return {
            "text": text,
            "text_native": str(text_native) if text_native else None,
            # "ready" only ever applies to real, auditee-authored content — an
            # empty entry carrying only a hypothetical example_suggestion must
            # never surface as ready, regardless of what the model returned.
            "verdict": verdict if text.strip() else "weak",
            "suggested_rewrite": str(suggested_rewrite) if suggested_rewrite else None,
            # Only meaningful when there's no real text yet; otherwise ignore it
            # so a model slip can't attach a hypothetical example to real content.
            "example_suggestion": str(example_suggestion) if example_suggestion and not text.strip() else None,
            "note": str(note) if note else None,
        }

    try:
        parsed = json.loads(cleaned)
        whys = [_normalize_entry(w) for w in parsed.get("whys", [])][:5]
        implemented_solution = _normalize_entry(parsed.get("implemented_solution", {}))
        # Trust but verify: overall_ready must never be true off the back of an
        # empty/example-only entry, regardless of what the model claims.
        overall_ready = bool(parsed.get("overall_ready", False)) and all(
            w["verdict"] == "ready" for w in whys
        ) and implemented_solution["verdict"] == "ready"
    except (json.JSONDecodeError, AttributeError):
        logger.error("Could not parse draft JSON for CAR %s: %r", focused_car.id, raw_reply)
        raise HTTPException(status_code=502, detail="Could not generate a draft, please try again.")

    return {"whys": whys, "implemented_solution": implemented_solution, "overall_ready": overall_ready}


async def upload_document(
    plant: str,
    email: str,
    access_mode: str,
    session_token: str,
    db: Session,
    file: UploadFile,
    car_id: int,
) -> dict:
    """Attach a text-based document (e.g. a customer requirement spec) to a
    CAR conversation so its extracted text gets injected into future chat
    turns for that CAR. Deliberately narrow: no OCR, no images, no vector
    store — see app/services/ai/document_parser.py for supported formats.
    """
    if not _client:
        raise HTTPException(status_code=503, detail="Chatbot is not configured")

    normalized_plant, normalized_email, normalized_mode = _authorize_portal_access(
        plant, email, access_mode, session_token, db
    )

    cars = car_service._query_auditee_portal_cars(
        normalized_plant, normalized_email, normalized_mode, db
    )
    focused_car = _resolve_focused_car(car_id, cars)

    filename = file.filename or "document"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in CHATBOT_DOCUMENT_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File type '{ext}' is not supported here. "
                f"Allowed: {', '.join(sorted(CHATBOT_DOCUMENT_EXTENSIONS))}"
            ),
        )

    content = await file.read()
    size = len(content)
    if size == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if size > CHATBOT_DOCUMENT_MAX_SIZE:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File too large ({size / 1_048_576:.1f} MB). "
                f"Max allowed: {CHATBOT_DOCUMENT_MAX_SIZE // 1_048_576} MB."
            ),
        )

    try:
        extracted = extract_text(filename, content)
    except DocumentParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    extracted = extracted.strip()
    if len(extracted) < MIN_EXTRACTED_CHARS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Could not find readable text in this document — it may be scanned or "
                "image-based. Please upload a text-based PDF, Word, or plain text file."
            ),
        )

    truncated = len(extracted) > MAX_DOCUMENT_CHARS
    if truncated:
        extracted = extracted[:MAX_DOCUMENT_CHARS]

    upload_result = blob_storage_service.upload_bytes_sync(
        content, folder="answers", filename=f"chatbot_{filename}"
    )

    now = datetime.now(timezone.utc)
    doc = PortalChatbotDocument(
        plant=normalized_plant,
        email=normalized_email,
        access_mode=normalized_mode,
        car_id=focused_car.id,
        filename=upload_result["filename"],
        blob_name=upload_result["blob_name"],
        file_url=upload_result["file_url"],
        mimetype=upload_result["mimetype"],
        size=size,
        extracted_text=extracted,
        truncated=truncated,
        created_at=now,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    return {
        "id": doc.id,
        "filename": doc.filename,
        "size": doc.size,
        "extracted_chars": len(extracted),
        "truncated": truncated,
    }


def list_documents(
    plant: str,
    email: str,
    access_mode: str,
    session_token: str,
    db: Session,
    car_id: int,
) -> list[dict]:
    normalized_plant, normalized_email, normalized_mode = _authorize_portal_access(
        plant, email, access_mode, session_token, db
    )
    cars = car_service._query_auditee_portal_cars(
        normalized_plant, normalized_email, normalized_mode, db
    )
    focused_car = _resolve_focused_car(car_id, cars)

    # Scoped by car_id alone (see _attached_documents_context) so every
    # auditee assigned to this CAR's audit sees the same attachment list,
    # regardless of who uploaded it or under which access_mode.
    docs = (
        db.query(PortalChatbotDocument)
        .filter_by(car_id=focused_car.id)
        .order_by(PortalChatbotDocument.created_at.desc())
        .all()
    )
    return [
        {
            "id": d.id,
            "filename": d.filename,
            "size": d.size,
            "truncated": d.truncated,
            "created_at": d.created_at,
        }
        for d in docs
    ]
