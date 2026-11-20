"""Regression tests for the generated VDA action-plan PDF layout.

Run from the backend root:
    python -m unittest tests.test_audit_report_layout -v
"""

import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from pypdf import PdfReader

from app.services.audit_report_service import generate_vda_audit_report


@contextmanager
def temporary_pdf_path():
    """Create a writable PDF path without relying on a system temp folder."""
    with tempfile.NamedTemporaryFile(
        dir=Path.cwd(), suffix=".pdf", delete=False
    ) as temp_file:
        output_path = Path(temp_file.name)
    try:
        yield output_path
    finally:
        output_path.unlink(missing_ok=True)


class VdaActionPlanLayoutTests(unittest.TestCase):
    def test_long_findings_wrap_and_action_table_paginates(self):
        finding = (
            "During the audit, the documented control and inspection requirements "
            "were not fully implemented on the production line. "
        ) * 3
        questions = [
            {
                "question_code": f"P6.2.{index}",
                "element": "P6",
                "process": "Product",
                "finding_text": finding,
                "value": 0,
                "corrective_action": [],
            }
            for index in range(1, 19)
        ]
        audit_data = {
            "report_profile": "VDA",
            "audit_number": "LAYOUT-REGRESSION",
            "audit_date": "2026-09-28T07:00:00",
            "plant": "Test Plant",
            "auditees": ["Supplier Quality Team"],
            "sector": "Production",
            "type": "Process audit",
            "total_score": 72.0,
            "summary": "Layout verification report",
            "strong_points": "Document control",
            "weak_points": "Implementation gaps",
            "detailed_questions": questions,
            "section_titles": {"P6": "Process analysis / production"},
        }

        with temporary_pdf_path() as output_path:
            generate_vda_audit_report(audit_data, output_path)
            reader = PdfReader(output_path)
            action_pages = [
                page.extract_text() or ""
                for page in reader.pages
                if "Action plan with defined immediate action"
                in (page.extract_text() or "")
            ]

        self.assertGreater(
            len(action_pages),
            1,
            "A long action plan should split across multiple pages.",
        )
        for page_text in action_pages:
            self.assertIn("Question No.", page_text)
            self.assertIn("Audit results", page_text)

        extracted_lines = "\n".join(action_pages).splitlines()
        finding_lines = [
            line
            for line in extracted_lines
            if "documented control" in line or "production line" in line
        ]
        self.assertGreater(len(finding_lines), len(questions))
        self.assertLess(
            max(map(len, finding_lines)),
            100,
            "Long findings should wrap instead of overflowing adjacent columns.",
        )
        self.assertIn("P6.2.18", "\n".join(action_pages))

    def test_one_oversized_finding_continues_on_following_pages(self):
        finding = (
            "Exceptionally long finding content must remain inside the printable "
            "action plan area. "
        ) * 180 + "END-OF-FINDING"
        audit_data = {
            "report_profile": "VDA",
            "audit_number": "TALL-ROW-REGRESSION",
            "audit_date": "2026-09-28",
            "plant": "Test Plant",
            "total_score": 72.0,
            "detailed_questions": [
                {
                    "question_code": "P6.2.999",
                    "element": "P6",
                    "process": "Product",
                    "finding_text": finding,
                    "value": 0,
                    "corrective_action": [],
                }
            ],
        }

        with temporary_pdf_path() as output_path:
            generate_vda_audit_report(audit_data, output_path)
            reader = PdfReader(output_path)
            action_pages = [
                page.extract_text() or ""
                for page in reader.pages
                if "Action plan with defined immediate action"
                in (page.extract_text() or "")
            ]

        self.assertGreater(len(action_pages), 1)
        self.assertNotIn("END-OF-FINDING", "\n".join(action_pages[:-1]))
        self.assertIn("END-OF-FINDING", action_pages[-1])
        for page_text in action_pages:
            self.assertIn("Question No.", page_text)
            self.assertIn("Audit results", page_text)


if __name__ == "__main__":
    unittest.main()
