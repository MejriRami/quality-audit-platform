"""Tests for the findings-based (non-VDA) consolidated report.

Run from the backend root:
    python -m unittest tests.test_consolidation_report -v
"""

import unittest
from io import BytesIO

from pypdf import PdfReader

from app.services.consolidation_report_service import (
    build_consolidated_findings,
    generate_consolidated_findings_report,
)


def _iatf_audit(number, questions, score=50.0):
    return {
        "audit_number": number,
        "plant": "Test Plant",
        "auditor": "Jane Auditor",
        "questionnaire_name": "IATF 16949:2016",
        "audit_date": "2026-10-12 08:30",
        "total_score": score,
        "result_class": None,
        "strong_points": "No strong points documented.",
        "weak_points": "NA",
        "report_profile": "IATF_NC",
        "detailed_questions": questions,
    }


def _nc(clause, classification, reason="", status="fail"):
    cars = (
        [{"action_type": "corrective", "status": "pending", "reason_why": reason,
          "due_date": "2026-10-27"}]
        if reason else []
    )
    return {
        "standard_paragraph": clause,
        "classification": classification,
        "process": "C5 Logistics",
        "question_text": "No description",
        "finding_text": "",
        "status": status,
        "corrective_action": cars,
    }


class IatfConsolidationTests(unittest.TestCase):
    def setUp(self):
        self.audits = [
            _iatf_audit("A-1", [
                _nc("9.1 Monitoring", "Minor", "KPI file not up to date"),
                _nc("6.1 Risks", "Major", "No risk analysis for 2026"),
                _nc("8.5.1", "Strong Point", status="pass"),
            ], score=68.0),
            _iatf_audit("A-2", [
                _nc("8.7 Nonconforming outputs", "Minor", "Quarantine area not controlled"),
                _nc("C3 _ Product design", "Improvement"),
            ], score=0.0),
        ]

    def test_findings_use_car_text_and_skip_strong_points(self):
        findings = build_consolidated_findings(self.audits, "IATF_NC")

        self.assertEqual(len(findings), 4)
        by_clause = {f["reference"]: f for f in findings}
        self.assertEqual(by_clause["9.1 Monitoring"]["description"], "KPI file not up to date")
        self.assertEqual(by_clause["9.1 Monitoring"]["theme"], "Clause 9 - Performance evaluation")
        self.assertEqual(by_clause["6.1 Risks"]["severity"], "Major")
        # Non-numeric clauses get their own theme instead of being dropped.
        self.assertEqual(by_clause["C3 _ Product design"]["theme"], "C3 _ Product design")

    def test_pdf_lists_each_audit_score_and_finding(self):
        findings = build_consolidated_findings(self.audits, "IATF_NC")
        pdf = generate_consolidated_findings_report(self.audits, findings, "IATF_NC")
        text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(pdf)).pages)

        self.assertIn("68%", text)
        self.assertIn("Quarantine area not controlled", text)
        self.assertIn("Clause 6 - Planning", text)
        self.assertNotIn("VDA", text)
        self.assertNotIn("Mahle", text)


class StandardConsolidationTests(unittest.TestCase):
    def test_failed_and_improve_answers_become_findings(self):
        audits = [
            {
                "audit_number": "S-1",
                "plant": "Test Plant",
                "questionnaire_name": "5S Audit",
                "total_score": 80.0,
                "report_profile": "STANDARD",
                "detailed_questions": [
                    {"question_text": "Floor is clean", "chapter": "Shine", "status": "fail",
                     "finding_text": "Oil on the floor", "question_code": "S3.1"},
                    {"question_text": "Labels present", "chapter": "Sort", "status": "improve"},
                    {"question_text": "Tools stored", "chapter": "Sort", "status": "pass"},
                ],
            },
        ]
        findings = build_consolidated_findings(audits, "STANDARD")

        self.assertEqual([f["severity"] for f in findings], ["Fail", "Improve"])
        self.assertEqual(findings[0]["description"], "Floor is clean\nOil on the floor")

        pdf = generate_consolidated_findings_report(audits, findings, "STANDARD")
        text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(pdf)).pages)
        self.assertIn("Oil on the floor", text)


if __name__ == "__main__":
    unittest.main()
