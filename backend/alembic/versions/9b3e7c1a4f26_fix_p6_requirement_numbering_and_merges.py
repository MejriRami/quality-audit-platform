"""fix P6 requirement numbering and merged rows

Revision ID: 9b3e7c1a4f26
Revises: 8f04da99ebe5
Create Date: 2026-09-01 00:00:00.000000

"""
import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b3e7c1a4f26'
down_revision: Union[str, Sequence[str], None] = '8f04da99ebe5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# The VDA6.3 question bank import for element P6 (questions 6.1-6.6) had two
# bugs, found by comparing the database against the source "Audit VDA6.3.xlsm"
# reference file question by question:
#
# 1. Each question's sub-requirements are organised into named sub-groups in
#    the source file (e.g. 6.6.1, 6.6.2, 6.6.3, 6.6.4 under question 6.6),
#    each holding several unnumbered detail bullets. The import mistakenly
#    used each bullet's position *within* its sub-group as if it were the
#    bullet's own unique code, restarting the counter at 1 for every
#    sub-group. That made unrelated bullets from different sub-groups share
#    the same requirement_code (e.g. four different requirements all labelled
#    "P6.6.1"). The fix below re-derives the true sub-group boundaries from
#    the existing (buggy) per-bullet reset pattern - a reset back to ".1" is
#    exactly where a new source sub-group began - and relabels every bullet
#    in a sub-group with that sub-group's own code, matching the source file.
#
# 2. In 15 places, two (in two cases, three) consecutive source bullets were
#    concatenated into a single database row instead of being imported as
#    separate rows. SPLIT_FRAGMENTS below holds the exact original wording
#    (verified against the source file) to split each one back apart. Two
#    further source lines have no fix here: their English cell was blank in
#    the source file itself (French-only), so there is no English wording to
#    restore - those remain merged into their neighbouring bullet.
#
# Separately, at three chapter boundaries (end of question 4.8, 5.7, 6.6) the
# import saved the *next* chapter's title as if it were a real requirement
# ("Supplier Management", "Process analysis / production", "Customer care /
# customer satisfaction / service" - none of these are real audit
# requirements). Two of them already carry a harmless answer (fulfilled=True,
# no finding text, no evidence) from completed audits #867 and #419; these are
# removed along with their fake master row.
PHANTOM_REQUIREMENT_IDS = (125, 153, 289)

# requirement_id -> (first fragment, second fragment), exact wording from the
# source file's English column.
SPLIT_FRAGMENTS = {
    154: (
        "The project transfer to serial production has been carried out. If necessary, unresolved issues are followed up on and implemented on schedule. ",
        "The responsibilities for the entire handover process are regulated and acknowledged.",
    ),
    159: (
        "The correct product (incoming material, part, component etc.) must be provided to the agreed quality, in the correct quantity and the correct packing, with the correct documentation, at the agreed time and at the agreed place.",
        "Parts/components must be available at defined storage areas/work-stations.",
    ),
    163: (
        "During manufacture and internal transport and also when being transported to and from service companies, ",
        "suitable transport units must be used to protect the products from damage and contamination.",
    ),
    177: (
        "According to customer requirements changes to the product and process are to be agreed upon, approved and released by the customer (including software changes).",
        "If necessary a new PPA must be carried out. Documentation of change status must be fully traceable.",
    ),
    185: (
        "For products with specific requirements on the manufacturing process the appropriate data about machinery/ tools/resources ",
        "must be noted in the control plan and/or the manufacturing and inspection documents.",
    ),
    202: (
        "Appropriate measures and checks must be taken to ensure the early detection and ejection of incorrectly installed items.",
        "Associated topics and actions must be included and examined in the risk analysis (process FMEA and, if appropriate, in the product FMEA).",
    ),
    204: (
        "The reuse of residual quantities, separated parts, reworked parts, reusable parts from product audits, inspected items etc. must be clearly defined ",
        "(including regulations for traceability).",
    ),
    214: (
        "Responsibilities, duties and authority of the employees in their task areas are described and implemented ",
        "(e.g. process release, first piece inspection, employee self-inspections, stopping the process).",
    ),
    225: (
        "The process capability must meet the customer requirements. For long term process capability the minimum requirement of Cpk ≥ 1,33 must be met. ",
        "In the case of significant characteristics where no capability level can be proven, 100% inspection is required.",
    ),
    233: (
        "Tools undergo a tool management which includes the following:",
        "Status indication (e.g. OK, NOK)\nTool life cycle including all changes made to the tool\nTool life\nTool ownership (e.g. customer ownership)",
    ),
    235: (
        "Capability studies are carried out on the test an measuring equipment/facilities employed. There is an identification system for test and measuring equipment. ",
        "Administration of this equipment is based on the identification.",
    ),
    236: (
        "A process for the periodic monitoring of measurement and inspection equipment is installed and implemented (responsibility for collection and return is defined).",
        "This process also takes into account the calibration of process-integrated measurement technology with an influence on the product characteristics.",
    ),
    256: (
        "If deviations from product and process requirements occur, immediate containment actions must be taken to comply with the requirements,",
        "until the causes of failure are eliminated and evidence has been provided of the effectiveness of the  corrective actions. These actions are known by the employees.",
    ),
    264: (
        "Product audits are periodically carried out and documented. Scope of the audit is the end product an where necessary intermediate products. ",
        "In the product audit specified characteristics are examined an tested according to defined specifications.",
    ),
    279: (
        "Concessions/deviation approvals must be traceable by appropriate identification and documentation. The documentation must cover the period and/or quantity of parts involved. ",
        "These details are documented including the identification on the component/carrier.",
    ),
}

QUESTION_CODES = ["P6.1", "P6.2", "P6.3", "P6.4", "P6.5", "P6.6"]


def _renumber_and_split(bind, question_code: str, apply_splits: bool) -> None:
    parent_num = question_code[1:]  # "P6.6" -> "6.6"

    rows = bind.execute(
        sa.text(
            """
            SELECT qr.id, qr.description, qr.requirement_code, qr.sort_order
            FROM question_requirements qr
            JOIN questions q ON q.id = qr.question_id
            WHERE q.question_code = :code
              AND q.questionnaire_id = 1
              AND qr.requirement_code NOT LIKE '%.0'
            ORDER BY qr.sort_order
            """
        ),
        {"code": question_code},
    ).mappings().all()
    if not rows:
        return
    question_id = bind.execute(
        sa.text(
            "SELECT id FROM questions WHERE question_code = :code AND questionnaire_id = 1"
        ),
        {"code": question_code},
    ).scalar_one()

    # Re-derive the true source sub-group boundaries: a reset of the local
    # index back to 1 marks the start of a new sub-group in the source file.
    chunks = []
    current = []
    for row in rows:
        m = re.search(r"\.(\d+)$", row["requirement_code"] or "")
        n = int(m.group(1)) if m else None
        if n == 1 and current:
            chunks.append(current)
            current = []
        current.append(row)
    if current:
        chunks.append(current)

    plan = []  # list of ("update", id, code, description) | ("insert", code, description)
    for chunk_index, chunk in enumerate(chunks, start=1):
        subgroup_code = f"P{parent_num}.{chunk_index}"
        for row in chunk:
            fragments = SPLIT_FRAGMENTS.get(row["id"]) if apply_splits else None
            if fragments:
                plan.append(("update", row["id"], subgroup_code, fragments[0]))
                plan.append(("insert", subgroup_code, fragments[1]))
            else:
                plan.append(("update", row["id"], subgroup_code, row["description"]))

    for sort_order, item in enumerate(plan, start=1):
        if item[0] == "update":
            _, row_id, code, description = item
            bind.execute(
                sa.text(
                    """
                    UPDATE question_requirements
                    SET requirement_code = :code, description = :description, sort_order = :sort_order
                    WHERE id = :id
                    """
                ),
                {"code": code, "description": description, "sort_order": sort_order, "id": row_id},
            )
        else:
            _, code, description = item
            bind.execute(
                sa.text(
                    """
                    INSERT INTO question_requirements (question_id, requirement_code, description, sort_order)
                    VALUES (:question_id, :code, :description, :sort_order)
                    """
                ),
                {"question_id": question_id, "code": code, "description": description, "sort_order": sort_order},
            )


def upgrade() -> None:
    bind = op.get_bind()

    bind.execute(
        sa.text(
            "DELETE FROM audit_answer_requirements WHERE question_requirement_id = ANY(:ids)"
        ),
        {"ids": list(PHANTOM_REQUIREMENT_IDS)},
    )
    bind.execute(
        sa.text("DELETE FROM question_requirements WHERE id = ANY(:ids)"),
        {"ids": list(PHANTOM_REQUIREMENT_IDS)},
    )

    for question_code in QUESTION_CODES:
        _renumber_and_split(bind, question_code, apply_splits=True)


def downgrade() -> None:
    # Best-effort only: merges the split rows back into their original
    # concatenated text and removes the rows this migration inserted. The
    # per-bullet numbering is left corrected (re-introducing the original
    # duplicate-code bug serves no purpose) and the three deleted phantom
    # "chapter title" rows are not restored, since the harmless completed-
    # audit answers that referenced two of them were deleted along with them
    # and cannot be reconstructed.
    bind = op.get_bind()
    for row_id, (first, second) in SPLIT_FRAGMENTS.items():
        merged = first + (" " if not first.endswith((" ", "\n")) else "") + second
        bind.execute(
            sa.text(
                """
                DELETE FROM question_requirements
                WHERE question_id = (SELECT question_id FROM question_requirements WHERE id = :id)
                  AND description = :second
                  AND id <> :id
                """
            ),
            {"id": row_id, "second": second},
        )
        bind.execute(
            sa.text("UPDATE question_requirements SET description = :merged WHERE id = :id"),
            {"merged": merged, "id": row_id},
        )
