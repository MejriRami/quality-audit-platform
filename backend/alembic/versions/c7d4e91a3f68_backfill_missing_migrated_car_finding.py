"""backfill missing finding text on migrated CARs

Revision ID: c7d4e91a3f68
Revises: 9b3e7c1a4f26
Create Date: 2026-09-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7d4e91a3f68'
down_revision: Union[str, Sequence[str], None] = '9b3e7c1a4f26'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# The Monday.com -> Postgres migration script never populated the `finding`
# column at all (it's not in that INSERT's column list - it was meant to be
# backfilled separately). A later, undocumented backfill did populate it for
# most migrated CARs, but missed 37. Of those, these 17 were re-identified
# with high confidence by joining each CAR's existing root_cause /
# implemented_solution / reason_why text (and, where that was insufficient,
# its audit's plant + auditee + date) against a fresh Monday.com export of
# the same board - the Monday item's "Name" field is the actual
# non-conformity description.
#
# Three of these (943, 940, 918) are truncated mid-sentence - not by this
# migration or by the export tooling, but by Monday.com itself: its own API
# returns the exact same truncated text, so the full original wording was
# never stored anywhere and cannot be recovered.
#
# The remaining 20 of the original 37 have no reliable unique match (several
# findings on the same audit share identical boilerplate root-cause text with
# no other distinguishing field) and are intentionally left for manual
# review rather than guessed at.
FINDING_BACKFILL = {
    1804: "The KPI “Conception produit : livrer au client des plans” for Northwind was not achieved for June and September, and no action plan has been defined to address these deviations.",
    1800: "1/A discrepancy was identified between the DMS and the control plan (CP-TRP-002) regarding the electrode change frequency. The DMS specifies that the electrode change should be performed after 3000 cycles, whereas the control plan states that the ele",
    1803: "1/Non-conforming products were observed in the red box without proper identification or segregation status. Furthermore, no Quality Rejection and Analysis Process Report (QRAP) had been initiated for the detected non-conformities, and no documented r",
    1765: "Lack of cleaning of the glasses",
    1766: "Lack of cleaning of the glasses",
    1769: "No SOP was completed on June 27, 2025, at 6 PM for the force test",
    1770: "The SOP for force test was not completed on July 03,2025 at 6 A.M",
    1773: "No tracking of the use of the glasses",
    1774: "Failure to charge the glasses after use",
    1775: "No formal booking process via Outlook Meeting for the connected glasses, which may cause availability issues and conflicts",
    1776: "No Change management procedure is implemented",
    1777: "4M change management not displayed in the shopfloor, No evidence shown for the signed training for operators ad midle managers (production and Quality",
    1779: "No structured complaint handling process (8D or equivalent), containment actions, root cause analysis, or corrective actions were demonstrated.",
    1782: "Backlog on customer demand , root cause is repeated late deliveries linked to the supplier’s aging equipment, with no defined action plan in place to correct the issue.",
    1792: "No CSR review for Dolz customer",
    1795: "The CSR has not been reviewed since the latest update. The last review was on 06/01/2023, whereas the latest version was issued in 2025 (Revision 7)",
    1796: "No monthly supplier performance scorecard is communicated by DENSO, as required in Section d (Supplier Performance Monitoring System) of the CSR manual",
}


def upgrade() -> None:
    bind = op.get_bind()
    for car_id, finding in FINDING_BACKFILL.items():
        bind.execute(
            sa.text(
                """
                UPDATE corrective_actions
                SET finding = :finding
                WHERE id = :id AND (finding IS NULL OR finding = '')
                """
            ),
            {"finding": finding, "id": car_id},
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("UPDATE corrective_actions SET finding = NULL WHERE id = ANY(:ids)"),
        {"ids": list(FINDING_BACKFILL.keys())},
    )
