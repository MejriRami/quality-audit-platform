"""backfill more migrated CAR finding and question text

Revision ID: c65c9ba3e00c
Revises: e2f9a6c14d38
Create Date: 2026-09-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c65c9ba3e00c'
down_revision: Union[str, Sequence[str], None] = 'e2f9a6c14d38'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Second pass over the same gap the last two migrations (c7d4e91a3f68,
# e2f9a6c14d38) left for "manual review" - a fresh Monday.com export
# (8289608350_Audit Corrective Actions (2).xlsx, pulled 2026-09-02) supplied
# by the user made more of those matches resolvable.
#
# Matching method: for each migrated CAR still missing finding and/or
# question text, find export rows sharing the same audit (plant + audit
# date; corporate-function audits are labelled Plant="Group" in the export
# even though the DB recorded a specific plant, so plant-less date-only
# matching was used as a fallback there), then disambiguate within that
# audit by comparing root_cause/implemented_solution text, falling back to
# fuzzy-matching the CAR's existing (possibly truncated) `finding` text
# against the export's "Name" field. Only kept where exactly one export row
# matched with high confidence.
#
# Of 119 migrated CARs still missing finding and/or question text as of
# 2026-09-03, 10 finding values and 105 question values were
# recovered this way. The remaining ones are either genuinely blank in both
# the DB and the export (no distinguishing text at all - id 759, 825, 826)
# or share identical boilerplate root_cause/finding text with one or more
# sibling CARs on the same audit with no other distinguishing field (e.g.
# 136/137/1776 - three CARs, two matching export rows, all with the exact
# same finding text) - both categories are left for manual review rather
# than guessed at, same as the prior two passes.
#
# Separately (not handled by this migration): 54 migrated CARs have no
# audit_id at all (not just a missing auditee) - they were never linked to
# an audit during the original migration. 27 of those are still open. That
# needs its own investigation since there's no audit context here to match
# against, and is tracked separately.
FINDING_BACKFILL = {
    793: 'Traceability Inconsistency in Production : for part number A60101921, the 4000 pieces found in production showed a receipt date of 30/01/2026, which differs from the warehouse information (27/11/2025)',
    794: 'Traceability Inconsistency in Production : for part number A60101921, the 4000 pieces found in production showed a receipt date of 30/01/2026, which differs from the warehouse information (27/11/2025)',
    1755: 'No Poka-Yoke and no special characteristics symbols are indicated in Control Plan NEM2 (revision date: 17/09/2024, level: 52)',
    1756: 'For part numbers 615 and 745, after the electrical test, the products undergo a force test, but this operation is not mentioned in the CP',
    1760: 'According to CP PC4.4-M1 ind. 1 (ref: 1026621, creation date: 05/02/2025, index: 00), for operation 55 (radius grinding manual set operation), all SPC checks are performed every 1 hour, whereas in the SPC control card, they are listed as every 4 hour',
    1761: '1) There is no SPC (1 sample/hour) for parallelism as required in the CP (20.3)/ 2) There is no SPC (1 sample/hour) for Rz (20.4)',
    1762: 'Document inconsistency : In the SOP instruction , the vibration frequncy bow feeder is between 40-60Hz 5 while in the CP is 75Hz) , also for vibration frequency vibrating rail is between 60-80 Hz while in the CP is 97,8 Hz',
    1763: 'FIFO Principle Not Respected : For the part number A60101921, the warehouse operator issued 4000 pieces with a receipt date of 27/11/2025.However, stock verification showed the presence of older material with a receipt date of 07/11/2025.',
    1764: 'Inconsistency Between Physical Stock and System Records : In the raw materials warehouse, for part number A60101921, system verification revealed the following:No recorded movement corresponding to the withdrawal of the lot dated 27/11/2025 / No lot',
    1768: 'No evidence shown for the qualification of the quality inspectors',
}

QUESTION_BACKFILL = {
    281: 'Control plan respected (including records)',
    282: 'Control plan respected (including records)',
    426: 'Production instructions defined, validated and matches control plan (special characteristics, control plan-related operations, control cards and security rules)',
    428: 'Production instructions defined, validated and matches control plan (special characteristics, control plan-related operations, control cards and security rules)',
    431: 'Start Of Production instructions defined and respected (including records)',
    451: 'Production instructions defined, validated and matches control plan (special characteristics, control plan-related operations, control cards and security rules)',
    452: 'Production instructions defined, validated and matches control plan (special characteristics, control plan-related operations, control cards and security rules)',
    453: 'Production instructions defined, validated and matches control plan (special characteristics, control plan-related operations, control cards and security rules)',
    454: 'Control plan respected (including records)',
    476: 'Control plan respected (including records)',
    480: 'Control plan respected (including records)',
    483: 'Control plan respected (including records)',
    526: 'Start Of Production instructions defined and respected (including records)',
    530: 'Control plan respected (including records)',
    531: 'Control plan respected (including records)',
    532: 'Production instructions defined, validated and matches control plan (special characteristics, control plan-related operations, control cards and security rules)',
    533: 'Start Of Production instructions defined and respected (including records)',
    534: 'Control plan respected (including records)',
    535: 'Control plan respected (including records)',
    559: 'Workshop layout defined, adapted and flows optimized',
    560: 'Control plan respected (including records)',
    561: 'Control plan respected (including records)',
    562: 'Control plan respected (including records)',
    577: '6.2.1 Are the specificatons of the control plan complete and have they been ffectively implemented?',
    598: 'Production instructions defined, validated and matches control plan (special characteristics, control plan-related operations, control cards and security rules)',
    650: '6.4.2 Is the maintenance of the manufacturing  equipment and tools controlled?',
    724: '7.5.2.1 Revue et approbation des informations documentées',
    725: '7.5.3.2.1   Maîtrise des informations documentées',
    726: '7.5.2.1 Revue et approbation des informations documentées',
    736: '7.3 Is the suppl of parts guaranteed?',
    747: '6.2.1 Are the specificatons of the control plan complete and have they been ffectively implemented?',
    749: '6.1.5 Are changes f the roduct or the process made durig the serial production tracked and documented?',
    760: 'Spare parts list defined and parts available',
    761: 'Are employees engaged in Kaizen or suggestion programs?',
    762: 'Has the plant introduced new automation, lean, or Industry 4.0 practices?',
    767: 'Control of Documented Information',
    768: 'Review the C3: Product Design Flow chart with an example of current year design for assembly',
    769: 'Review the SWOT , Risk Analysis, are there action for each detected risks marked in the red zone? include the climatic change ? (copy)',
    770: 'Risk Analysis if feasible without pending actions? if yes, is there another final feasibility study with all closed actions?',
    771: 'Creating and updating documented information',
    772: 'Creating and updating documented information',
    773: 'Design and Development Controls',
    774: 'Design and Development Plan Update',
    775: 'Preservation',
    776: 'Design and Development Outputs',
    777: 'Monitoring, Measurement, Analysis and Evaluation',
    779: 'Are trainings on new or revised instructions conducted and documented to ensure that all concerned employees are informed and competent?',
    780: 'Is sales backlog tracked (including aging), with actions to reduce delays?',
    791: '7.2 Is customer service guaranteed?',
    792: '6.4.2 Is the maintenance of the manufacturing  equipment and tools controlled?',
    793: '6.1.4 Are the necessary identifications / records/ appovals available and allocated appropriately to the incoming materials?',
    794: '6.1.4 Are the necessary identifications / records/ appovals available and allocated appropriately to the incoming materials?',
    795: '6.1.4 Are the necessary identifications / records/ appovals available and allocated appropriately to the incoming materials?',
    804: '7.1 Are all requirements releaed to QM system, product and process fulfilled?',
    805: '7.2 Is customer service uaranteed?',
    806: '7.3 Is the suppl of parts guaranteed?',
    809: '6.4.2 Is the maintenance of the manufacturing  equipment and tools controlled?',
    810: '6.4.3 Can the quality requirements be effectively monitored with the measurement ans test facilities in used?',
    811: '6.5.4 Are process and products audited regularly ?',
    812: '5.4 ARe the necessary aprovals/ releases available for the outsources products and services?',
    813: '5.5 Is the quality of the outsouces products and services ensured?',
    814: '7.1 Are all requirements releaed to QM system, product and process fulfilled?',
    815: '7.2 Is customer service guaranteed?',
    816: '7.3 Is the supply of parts guaranteed?',
    817: '6.2.2 Does a repeat reease for the restart of roduction take place?',
    818: '6.4.2 Is the maintenance of the manufacturing  equipment and tools controlled?',
    819: '6.6.3 Are the necessary records/releases retained?',
    820: '6.6.3 Are the necessary records/releases retained?',
    821: '6.4.2 Is the maintenance of the manufacturing  equipment and tools controlled?',
    822: '6.4.2 Is the maintenance of the manufacturing  equipment and tools controlled?',
    829: '6.1.1 Has the proect been transferred from development to serial production and is a reliable start guaranted?',
    830: '6.2.4 Are non-released and/or defective parts managed?',
    831: '6.2.1 Are the specificatons of the control plan complete and have they been ffectively implemented?',
    832: '6.4.5 Are tools, equipment and test eauipment stored properly?',
    833: '6.5.1 Are there targets setfor the manufacturing process?',
    843: '6.2.2 Does a repeat reease for the restart of roduction take place?',
    846: '6.1.4 Are the necessary identifications / records/ appovals available and allocated appropriately to the incoming materials?',
    848: "5.2 ARe the customer' equirements taken into account in the supply chain?",
    849: '5.4 ARe the necessary aprovals/ releases available for the outsources products and services?',
    853: '5.1 Are only approved and quality capable supplier selected?',
    854: '5.1 Are only approved and quality capable supplier selected?',
    856: '6.5.1 Are there targets setfor the manufacturing process?',
    857: '6.5.3 In the case of eviations fro product and process requirements, are the causes analysed and the corrective actions checked for effectiveness?',
    1230: 'Production change instructions reliable and respected',
    1245: 'Start Of Production instructions defined and respected (including records)',
    1649: 'Inspectors qualified (control ability, product and customer requirements knowledge)',
    1650: 'Production instructions defined, validated and matches control plan (special characteristics, control plan-related operations, control cards and security rules)',
    1652: '7.4 If there are desviations from qualityrequirements or complaints, are failure analysis crried out and correctie actons implemented effectively?',
    1653: 'Traceability data recorded and archived',
    1654: 'PPAP file internally validated and up to date (drawings, process FMEA, control plan, material certificates and other documents)',
    1725: '9.3.2.1  Management review inputs',
    1726: 'Review the Management Review of the last year, include the KPI, IATF Processes evaluation, previous management review actions,',
    1727: 'Review the Strategic Plan of the site vs the Strategic Plan from Corporative-OS',
    1728: "Review overall KPI of the Plant. all indicators with targets. and defined action  plan for KPI didn't achieve the target",
    1729: 'Review the SWOT and Risk Analysis in the Global Management Strategic Fiie. P3-I1-E1. Is it update? risks are evaluated? verify as exigence 2025- if it  include the risk for climatic change? is at least  yearly updated?',
    1730: 'Review the web page of each customer to evaluate the Customer Ranking. If Northwind is in containment action or low ranking an action plan should be presented',
    1739: '9.1 Monitoring, measurement, analysis and evaluation',
    1755: 'Control plan respected (including records)',
    1756: 'Control plan respected (including records)',
    1760: 'Control plan respected (including records)',
    1761: 'Control plan respected (including records)',
    1762: 'Production instructions defined, validated and matches control plan (special characteristics, control plan-related operations, control cards and security rules)',
    1763: '6.1.2 Are the necessary quantities/ production batch sizes of incoming materials available at the agreed upon time and at the correct storage location/wok station?',
    1764: '6.1.3 Are incoming materials stored appropriately and are trsnsport facilities/packing arrangements suitable for the special characteristics of the ncoming materials?',
    1768: 'Inspectors qualified (control ability, product and customer requirements knowledge)',
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
    for car_id, question in QUESTION_BACKFILL.items():
        bind.execute(
            sa.text(
                """
                UPDATE corrective_actions
                SET migrated_question_text = :question
                WHERE id = :id
                  AND audit_answer_id IS NULL
                  AND (migrated_question_text IS NULL OR migrated_question_text = '')
                """
            ),
            {"question": question, "id": car_id},
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("UPDATE corrective_actions SET finding = NULL WHERE id = ANY(:ids)"),
        {"ids": list(FINDING_BACKFILL.keys())},
    )
    bind.execute(
        sa.text("UPDATE corrective_actions SET migrated_question_text = NULL WHERE id = ANY(:ids)"),
        {"ids": list(QUESTION_BACKFILL.keys())},
    )
