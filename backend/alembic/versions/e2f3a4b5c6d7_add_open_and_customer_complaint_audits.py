"""add open audit, customer complaint and IATF process owner audit types

Revision ID: e2f3a4b5c6d7
Revises: d8e1f2a3b4c5
Create Date: 2026-09-24 16:00:00.000000

- audit_answers.question_text: the question an auditor types in an Open audit.
- Audit types + ready-to-use questionnaires used by the monthly plan:
  * Open Audit            no fixed questions, score_calculation OPEN
  * Customer Complaint    CSL1 CSI/CSII checklist (P2/P3), 0/5/10 scoring
  * IATF Process Owner    process owner checklist (P8), 0/5/10 scoring
"""
from datetime import datetime, time, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, Sequence[str], None] = "d8e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CSL1_CHECKLIST = [
    ("Entry & exit", "Is the CSI/CSII entry & exit date defined?"),
    ("Responsibility", "Is the CSI/CSII responsible defined?"),
    ("Area", "Is the area to perform CSI/CSII defined? Are red / yellow containers available?"),
    ("Area", "Is the CSI/CSII area identified and delimited?"),
    (
        "Documentation",
        "Are the following documents published in the CSI/CSII area: drawing, CSI/CSII control "
        "instruction, report form, control graphics, list of trained CSI/CSII employees, "
        "packaging instruction?",
    ),
    ("Flow", "Is one-piece flow guaranteed?"),
    ("Inspection", "Are operators inspecting according to the inspection instruction?"),
    ("Daily management", "Is there a daily meeting to handle the daily rejections and action plan?"),
    (
        "Action plan",
        "Is there an engineering-level action plan to eliminate the causes of the findings? "
        "Are the action plan due dates respected?",
    ),
    (
        "Effectiveness",
        "Do the control graphs show a reduction of defects? Is the trend of the findings improving?",
    ),
    ("Master samples", "Are master samples available and identified?"),
    (
        "Measurement",
        "If a measurement tool is used to control the pieces, is it identified and calibrated? "
        "Is the instruction to use it available?",
    ),
    (
        "Communication",
        "Is there a shift-change meeting to discuss the findings, alerts and key messages? "
        "Is it documented?",
    ),
    (
        "Packaging",
        "During break times, are full boxes closed? If a box is not complete, is it identified "
        "as pending completion?",
    ),
]

IATF_PROCESS_OWNER_CHECKLIST = [
    ("KPI", "Are KPIs with targets defined and tracked on time?"),
    (
        "KPI",
        "Are the KPI targets achieved? In case of a gap, is an action plan defined based on "
        "root cause analysis?",
    ),
    (
        "Risk",
        "Is a risk analysis and action plan in place to eliminate or reduce the risk? Are "
        "climate changes considered in the risk analysis?",
    ),
    ("Process method", "Is the process method documented and updated on time?"),
    ("Process map", "Audit according to the documented process map."),
    (
        "People",
        "Is the team under your responsibility motivated and skilled, and does it have a "
        "semestrial performance evaluation?",
    ),
]

# (audit type, questionnaire name, framework code, score_calculation, questions)
NEW_AUDITS = [
    ("Open Audit", "Open Audit", "INTERNAL", "OPEN", []),
    ("Customer Complaint", "Customer Complaint - CSI/CSII Checklist (CSL1)", "INTERNAL", "INTERNAL", CSL1_CHECKLIST),
    ("IATF Process Owner", "IATF Process Owner Checklist", "IATF", "INTERNAL", IATF_PROCESS_OWNER_CHECKLIST),
]


def upgrade() -> None:
    op.add_column("audit_answers", sa.Column("question_text", sa.Text(), nullable=True))

    conn = op.get_bind()
    now = datetime.now(timezone.utc)
    for type_value, name, framework_code, score_calc, questions in NEW_AUDITS:
        type_id = conn.execute(
            sa.text("SELECT id FROM audit_types WHERE lower(value) = lower(:v)"), {"v": type_value}
        ).scalar()
        if type_id is None:
            type_id = conn.execute(
                sa.text("INSERT INTO audit_types (value) VALUES (:v) RETURNING id"), {"v": type_value}
            ).scalar()

        framework_id = conn.execute(
            sa.text("SELECT id FROM frameworks WHERE upper(code) = :c ORDER BY id LIMIT 1"),
            {"c": framework_code},
        ).scalar()
        if framework_id is None:
            raise RuntimeError(f"Framework '{framework_code}' not found")

        if conn.execute(
            sa.text("SELECT 1 FROM questionnaires WHERE name = :n"), {"n": name}
        ).scalar():
            continue
        questionnaire_id = conn.execute(
            sa.text(
                """
                INSERT INTO questionnaires
                    (name, target_duration, score_calculation, status, version,
                     created_at, framework_id, type_id)
                VALUES (:name, :duration, :calc, 'Ready to Use', 1, :now, :fw, :type)
                RETURNING id
                """
            ),
            {
                "name": name,
                "duration": time(2, 0),
                "calc": score_calc,
                "now": now,
                "fw": framework_id,
                "type": type_id,
            },
        ).scalar()
        # 0 / 5 / 10 scale: 5 = needs improvement, so it is the critical value.
        for index, (chapter, description) in enumerate(questions, start=1):
            conn.execute(
                sa.text(
                    """
                    INSERT INTO questions
                        (description, chapter, weight, critical_value, questionnaire_id,
                         question_code, is_asterisk)
                    VALUES (:d, :c, 1, 5, :q, :code, false)
                    """
                ),
                {"d": description, "c": chapter, "q": questionnaire_id, "code": str(index)},
            )


def downgrade() -> None:
    conn = op.get_bind()
    for type_value, name, *_ in NEW_AUDITS:
        in_use = conn.execute(
            sa.text(
                "SELECT count(*) FROM audits a JOIN questionnaires q ON q.id = a.questionnaire_id "
                "WHERE q.name = :n"
            ),
            {"n": name},
        ).scalar()
        if in_use:
            continue  # keep questionnaires that audits already reference
        conn.execute(
            sa.text(
                "DELETE FROM questions WHERE questionnaire_id IN "
                "(SELECT id FROM questionnaires WHERE name = :n)"
            ),
            {"n": name},
        )
        conn.execute(sa.text("DELETE FROM questionnaires WHERE name = :n"), {"n": name})
        conn.execute(
            sa.text(
                "DELETE FROM audit_types WHERE value = :v AND NOT EXISTS "
                "(SELECT 1 FROM questionnaires WHERE type_id = audit_types.id)"
            ),
            {"v": type_value},
        )
    op.drop_column("audit_answers", "question_text")
