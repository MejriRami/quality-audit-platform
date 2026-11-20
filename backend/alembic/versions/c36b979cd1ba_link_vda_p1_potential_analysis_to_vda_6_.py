"""link vda p1 potential analysis to vda 6.3

Revision ID: c36b979cd1ba
Revises: 39876a816767
Create Date: 2026-07-17 11:48:34.915003

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c36b979cd1ba'
down_revision: Union[str, Sequence[str], None] = '39876a816767'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "questionnaires",
        sa.Column("potential_analysis_questionnaire_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_questionnaires_potential_analysis_questionnaire_id",
        "questionnaires",
        "questionnaires",
        ["potential_analysis_questionnaire_id"],
        ["id"],
    )
    op.add_column(
        "audits",
        sa.Column(
            "include_potential_analysis",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "audits",
        sa.Column("potential_analysis_result_class", sa.String(length=5), nullable=True),
    )

    # Link "VDA 6.3 Process Audit" to "P1-Potential Analysis" by name (portable
    # across environments where ids may differ), and retire the standalone P1
    # questionnaire from audit planning without touching historical audits
    # that still reference it directly.
    op.execute(
        """
        UPDATE questionnaires
        SET potential_analysis_questionnaire_id = (
            SELECT id FROM questionnaires WHERE name = 'P1-Potential Analysis' LIMIT 1
        )
        WHERE name = 'VDA 6.3 Process Audit'
        """
    )
    op.execute(
        """
        UPDATE questionnaires
        SET status = 'Under Revision'
        WHERE name = 'P1-Potential Analysis'
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        """
        UPDATE questionnaires
        SET status = 'Ready to Use'
        WHERE name = 'P1-Potential Analysis'
        """
    )
    op.drop_column("audits", "potential_analysis_result_class")
    op.drop_column("audits", "include_potential_analysis")
    op.drop_constraint(
        "fk_questionnaires_potential_analysis_questionnaire_id",
        "questionnaires",
        type_="foreignkey",
    )
    op.drop_column("questionnaires", "potential_analysis_questionnaire_id")
