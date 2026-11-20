"""Tests for the internal complete report (with Silent Box findings).

Run from the backend root:
    python -m unittest tests.test_complete_report -v
"""

import unittest
from io import BytesIO

from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.routers.audit_report import _stamp_complete_report_banner


def _two_page_pdf() -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    for text in ("First page body", "Second page body"):
        c.drawString(72, 400, text)
        c.showPage()
    c.save()
    return buffer.getvalue()


class CompleteReportBannerTests(unittest.TestCase):
    def test_every_page_gets_the_internal_banner_and_keeps_its_content(self):
        stamped = PdfReader(BytesIO(_stamp_complete_report_banner(_two_page_pdf())))

        self.assertEqual(len(stamped.pages), 2)
        for page, body in zip(stamped.pages, ("First page body", "Second page body")):
            text = page.extract_text()
            self.assertIn("COMPLETE REPORT - INTERNAL", text)
            self.assertIn("[SB]", text)
            self.assertIn(body, text)


if __name__ == "__main__":
    unittest.main()
