"""add complaints + audit_candidates + links

Revision ID: 6133d94b14b9
Revises: 559b014d02d0
Create Date: 2026-02-05 12:14:17.739903

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '6133d94b14b9'
down_revision: Union[str, None] = '559b014d02d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    
    # ------------------------------------------------------------
    # 1) Ajouter priority_code à la table audits
    # ------------------------------------------------------------
    insp = inspect(bind)
    cols = [c["name"] for c in insp.get_columns("audits")]
    
    if "priority_code" not in cols:
        op.add_column("audits", sa.Column("priority_code", sa.String(length=5), nullable=True))
    
    # ------------------------------------------------------------
    # 2) Créer la table complaints
    # ------------------------------------------------------------
    op.create_table(
        "complaints",
        sa.Column("id", sa.Integer(), primary_key=True),
        
        sa.Column("item_id", sa.String(length=100), nullable=False),
        sa.Column("item_url", sa.Text(), nullable=False),
        
        # Plant en String au lieu d'enum
        sa.Column("plant", sa.String(length=100), nullable=True),
        sa.Column("product_line", sa.String(length=100), nullable=True),
        sa.Column("process_name", sa.String(length=100), nullable=True),
        
        sa.Column("complaint_description", sa.Text(), nullable=False),
        sa.Column("defects", sa.Text(), nullable=True),
        sa.Column("quality_issue_warranty", sa.Text(), nullable=True),
        
        sa.Column("repetitive_count", sa.Integer(), nullable=True),
        
        sa.Column("quality_manager", sa.String(length=100), nullable=True),
        sa.Column("plant_manager", sa.String(length=100), nullable=True),
        sa.Column("customer", sa.String(length=100), nullable=True),
        sa.Column("customer_plant_name", sa.String(length=100), nullable=True),
        
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("complaint_opening_date", sa.TIMESTAMP(), nullable=True),
        sa.Column("created_at_source", sa.TIMESTAMP(), nullable=True),
        
        sa.UniqueConstraint("item_id", name="uq_complaint_item_id"),
    )
    
    op.create_index("ix_complaint_status", "complaints", ["status"], unique=False)
    op.create_index("ix_complaint_scope_month", "complaints", ["plant", "product_line", "created_at_source"], unique=False)
    
    # ------------------------------------------------------------
    # 3) Créer la table audit_candidates
    # ------------------------------------------------------------
    op.create_table(
        "audit_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        
        sa.Column("priority_code", sa.String(length=5), nullable=False),
        sa.Column("candidate_type", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        
        # Plant en String au lieu d'enum
        sa.Column("plant", sa.String(length=100), nullable=False),
        sa.Column("product_line", sa.String(length=100), nullable=True),
        sa.Column("process_name", sa.String(length=100), nullable=True),
        
        sa.Column("target_month", sa.String(length=7), nullable=False),
        
        sa.Column("questionnaire_id", sa.Integer(), sa.ForeignKey("questionnaires.id"), nullable=True),
        sa.Column("audit_id", sa.Integer(), sa.ForeignKey("audits.id"), nullable=True),
        sa.Column("primary_complaint_id", sa.Integer(), sa.ForeignKey("complaints.id"), nullable=True),
        
        sa.Column("created_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=True),
        
        sa.UniqueConstraint(
            "priority_code", "candidate_type", "plant", "product_line", "process_name", "target_month",
            name="uq_candidate_scope_month"
        ),
    )
    
    op.create_index("ix_candidate_status_month", "audit_candidates", ["status", "target_month"], unique=False)
    
    # ------------------------------------------------------------
    # 4) Créer la table pivot audit_candidate_complaints
    # ------------------------------------------------------------
    op.create_table(
        "audit_candidate_complaints",
        sa.Column("id", sa.Integer(), primary_key=True),
        
        sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("audit_candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("complaint_id", sa.Integer(), sa.ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False),
        
        sa.Column("created_at", sa.TIMESTAMP(), nullable=True),
        
        sa.UniqueConstraint("candidate_id", "complaint_id", name="uq_candidate_complaint"),
    )
    
    op.create_index("ix_acc_candidate", "audit_candidate_complaints", ["candidate_id"], unique=False)
    op.create_index("ix_acc_complaint", "audit_candidate_complaints", ["complaint_id"], unique=False)


def downgrade() -> None:
    # Supprimer dans l'ordre inverse
    op.drop_index("ix_acc_complaint", table_name="audit_candidate_complaints")
    op.drop_index("ix_acc_candidate", table_name="audit_candidate_complaints")
    op.drop_table("audit_candidate_complaints")
    
    op.drop_index("ix_candidate_status_month", table_name="audit_candidates")
    op.drop_table("audit_candidates")
    
    op.drop_index("ix_complaint_scope_month", table_name="complaints")
    op.drop_index("ix_complaint_status", table_name="complaints")
    op.drop_table("complaints")
    
    op.drop_column("audits", "priority_code")
