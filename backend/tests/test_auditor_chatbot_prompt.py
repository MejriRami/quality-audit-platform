"""Unit tests for the auditor assistant's system prompt (no DB / network).

Run from the backend root:  python -m unittest tests.test_auditor_chatbot_prompt -v
"""

import unittest
from datetime import date, datetime
from types import SimpleNamespace as NS

from app.services.auditor_chatbot_service import build_system_prompt

TODAY = date(2026, 9, 29)
USER = NS(first_name="Jordan", last_name="Sellami")


def audit(number="M-POI-20260901-001", questionnaire="VDA 6.3", score=None):
    return NS(
        audit_number=number,
        plant="poitiers",
        questionnaire=NS(name=questionnaire) if questionnaire else None,
        status="completed",
        planned_start_date=datetime(2026, 9, 1, 8),
        actual_start_date=datetime(2026, 9, 1, 8),
        total_score=score,
        result_class="B" if score else None,
    )


class AuditorPromptTests(unittest.TestCase):
    def prompt(self, **kw):
        base = dict(global_scope=False, audits=[], open_cars=[], findings=[], plan_items=[])
        base.update(kw)
        return build_system_prompt(USER, today=TODAY, **base)

    def test_empty_data_is_stated_not_invented(self):
        p = self.prompt()
        self.assertIn("Jordan Rossi", p)
        self.assertIn("No open corrective actions.", p)
        self.assertIn("No upcoming audits in the monthly plan.", p)
        self.assertIn("audits you lead", p)

    def test_audits_cars_and_plan_are_listed(self):
        a = audit(score=84.25)
        car = NS(
            identifier="CA-1", id=1, audit=a, status="pending",
            due_date=date(2026, 9, 20), auditee=NS(email="user690@example.com"),
            finding="Alert threshold not defined", answer=None, reason_why="",
            action_type="corrective",
        )
        item = NS(
            scheduled_date=date(2026, 10, 7), plant="carthage", product_line="choke",
            trigger_codes=["P1"], checklist="Open Audit: Audit the 8D",
            auditee_name=None, auditee_role="Quality engineers",
        )
        p = self.prompt(global_scope=True, audits=[a, audit("M-POI-1", questionnaire=None)],
                        open_cars=[car], plan_items=[item])
        self.assertIn("M-POI-20260901-001 | poitiers | VDA 6.3 | status completed", p)
        self.assertIn("score 84.2 (B)", p)
        self.assertIn("imported from Monday", p)
        self.assertIn("due 2026-09-20 LATE", p)
        self.assertIn("2026-10-07 | same | choke | P1", p)
        self.assertIn("all audits", p)


if __name__ == "__main__":
    unittest.main()
