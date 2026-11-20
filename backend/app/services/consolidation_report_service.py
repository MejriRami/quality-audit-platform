"""
Cross-Audit Consolidation Reports

VDA 6.3 audits use generate_consolidated_vda_report (below); every other
report profile uses generate_consolidated_findings_report (end of file).

The VDA report builds a single PDF that merges the raw answers of several audits of the
same plant + questionnaire into ONE virtual VDA 6.3 evaluation — same
scoring engine (compute_vda_results) as a single audit — and renders it
with the layout of the individual VDA report
(audit_report_service.generate_vda_audit_report), extended with dedicated
per-audit sections so each source audit's own content stays individually
attributable instead of being collapsed into the merged view:

  Page 1: Audit-result + statements panel for the merged/virtual audit.
  Page(s): Per-Audit Summary, Findings and Conclusion — one labeled block
      per source audit with its own Summary of the audit carried out,
      Strengths, Opportunities for Improvement, Conclusion, Further
      action, and Schedule of action plan. Missing data (e.g. "n.e.",
      no confirmation/effectiveness date) is shown explicitly rather
      than the section being dropped.
  Page(s): Per-Audit Detailed Evaluation Matrix — each source audit's own
      P2-P7 element ratings (Answered/Total, Achieved/Max, EG%, Display
      A/B/C), independent of the merged matrix below.
  Page: Consolidated Detailed Evaluation Matrix for the merged/virtual
      audit (same shape as the single-audit report's matrix page).
  Page: Action plan with defined immediate action, grouped by element,
      with an extra "Audit" column so a merged row can be traced back to
      the audit it came from.
"""

from io import BytesIO
from typing import Any, Dict, List

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

DARK_GREEN = colors.HexColor("#006B3D")
BLACK = colors.black
WHITE = colors.white

VDA_ELEMENT_LABELS = {
    "P2": "Project management",
    "P3": "Planning the product and process development",
    "P4": "Implementation of product and process development",
    "P5": "Supplier management",
    "P6": "Process analysis / production",
    "P7": "Customer care / service",
}


def _fmt_pct(value):
    return "n.e." if value is None else f"{float(value):.1f}%"


def _fmt_display(value):
    return "n.e." if value is None else str(value)


def _fmt_field(value):
    """Explicit 'n.e.' for missing/blank data instead of silently dropping
    the field (schedule-of-action-plan dates, free-text summaries, ...)."""
    text = str(value).strip() if value is not None else ""
    return text if text else "n.e."


def _rating_for_score(eg_percent, result_class):
    if result_class:
        return result_class
    if eg_percent is None:
        return "n.e."
    eg_num = float(eg_percent)
    return "A" if eg_num >= 90 else "B" if eg_num >= 80 else "C"


def generate_consolidated_vda_report(
    audits_meta: List[dict],
    vda_result: Dict[str, Any],
    action_plan_rows: List[dict],
) -> bytes:
    """Render the consolidated VDA 6.3 report to PDF bytes (in-memory).

    audits_meta: one dict per merged audit — audit_number, plant, auditor,
        audit_date, total_score, result_class, strong_points, weak_points.
    vda_result: output of vda_scoring_service.compute_vda_results() run on
        the concatenated answers/questions of every merged audit.
    action_plan_rows: one dict per answered question across all merged
        audits — audit_number, element, question_code, chapter, value,
        critical_value, finding_text, corrective_action.
    """
    buffer = BytesIO()
    page_width, page_height = landscape(A4)
    c = canvas.Canvas(buffer, pagesize=landscape(A4))

    audit_numbers = [a["audit_number"] for a in audits_meta]
    plants = sorted({a["plant"] for a in audits_meta})
    plant_label = ", ".join(plants) or "N/A"
    questionnaire_name = next(
        (a.get("questionnaire_name") for a in audits_meta if a.get("questionnaire_name")),
        "VDA 6.3 Process Audit",
    )
    dates = sorted(d for d in (a.get("audit_date") for a in audits_meta) if d and d != "N/A")
    date_range = f"{dates[0]} - {dates[-1]}" if dates else "N/A"

    total = vda_result.get("total", {})
    total_eg = total.get("eg_percent")
    total_rating = total.get("final_rating", "n.e.")

    # ================= PAGE 1: Audit result + Statements =================
    ml, mr = 30, 30
    curr_y = page_height - 30

    c.setFont("Helvetica", 9)
    c.drawString(ml, curr_y, "VDA 6.3 Prozessaudit Revision 2016")
    curr_y -= 12
    c.setLineWidth(1)
    c.line(ml, curr_y, page_width - mr, curr_y)
    curr_y -= 20

    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(
        page_width / 2, curr_y, "Audit report VDA 6.3 Evaluation of quality capability"
    )
    curr_y -= 15
    c.setFont("Helvetica", 8.5)
    c.drawCentredString(
        page_width / 2,
        curr_y,
        f"Consolidated report — {len(audits_meta)} audits merged: {', '.join(audit_numbers)}",
    )
    curr_y -= 20

    def draw_info_row(x, y, label, value):
        c.setFont("Helvetica-Bold", 8)
        c.drawString(x, y, label)
        label_w = c.stringWidth(label, "Helvetica-Bold", 8)
        c.setFont("Helvetica", 8)
        c.drawString(x + label_w + 5, y, str(value))

    draw_info_row(ml, curr_y, "Supplier:", plant_label)
    draw_info_row(ml + 330, curr_y, "Date range:", date_range)
    curr_y -= 18
    draw_info_row(ml, curr_y, "Location:", plant_label)
    draw_info_row(ml + 330, curr_y, "Questionnaire:", questionnaire_name)
    curr_y -= 18
    draw_info_row(ml, curr_y, "Audit Reason:", "Process (Consolidated)")
    draw_info_row(ml + 330, curr_y, "Audits merged:", str(len(audits_meta)))
    curr_y -= 30

    left_w = 340
    right_w = (page_width - ml - mr) - left_w - 15

    normal_style = ParagraphStyle("Normal", fontName="Helvetica", fontSize=7, leading=9)
    bold_style = ParagraphStyle("Bold", fontName="Helvetica-Bold", fontSize=7, leading=9)
    header_style = ParagraphStyle(
        "Header", fontName="Helvetica-Bold", fontSize=8, textColor=WHITE, leading=10
    )

    strengths_items = [
        f"<b>{a['audit_number']}:</b> {a['strong_points']}"
        for a in audits_meta
        if (a.get("strong_points") or "").strip()
        and a["strong_points"].strip().lower() != "no strong points documented."
    ]
    opportunities_items = [
        f"<b>{a['audit_number']}:</b> {a['weak_points']}"
        for a in audits_meta
        if (a.get("weak_points") or "").strip()
        and a["weak_points"].strip().lower() != "no weak points documented."
    ]
    findings_text = (
        "<b>Strengths</b><br/>"
        + ("<br/>".join(strengths_items) or "No strong points documented.")
        + "<br/><br/><b>Opportunities for Improvement</b><br/>"
        + ("<br/>".join(opportunities_items) or "NA")
    )
    summary_text = (
        f"Consolidated evaluation covering {len(audits_meta)} audits "
        f"({', '.join(audit_numbers)})."
    )
    conclusion_text = f"Consolidated audit result {_fmt_pct(total_eg)} rated {total_rating}."

    right_data = [
        [Paragraph("Statements / Requirements", header_style)],
        [Paragraph("Summary of the audit carried out", bold_style)],
        [Paragraph(summary_text, normal_style)],
        [Paragraph("During the audit the following significant findings were identified:", bold_style)],
        [Paragraph(findings_text, normal_style)],
        [Paragraph("Conclusion", header_style)],
        [Paragraph(conclusion_text, normal_style)],
        [Paragraph("Further action", header_style)],
        [Paragraph("Action plan should be delivered to Mahle 10 working days after receiving this file.", normal_style)],
        [Paragraph("Schedule of action plan", header_style)],
    ]
    right_data.append(
        [
            Paragraph("Confirmation of measures", bold_style),
            Paragraph("", normal_style),
            Paragraph("Effectiveness check", bold_style),
            Paragraph("", normal_style),
        ]
    )

    rt = Table(right_data, colWidths=[right_w / 4] * 4)
    for i in range(10):
        rt.setStyle(TableStyle([("SPAN", (0, i), (3, i))]))
    rt.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (3, 0), DARK_GREEN),
                ("BACKGROUND", (0, 5), (3, 5), DARK_GREEN),
                ("BACKGROUND", (0, 7), (3, 7), DARK_GREEN),
                ("BACKGROUND", (0, 9), (3, 9), DARK_GREEN),
                ("GRID", (0, 0), (-1, -1), 0.5, BLACK),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    rt_w, rt_h = rt.wrap(right_w, page_height)
    rt.drawOn(c, ml + left_w + 15, curr_y - rt_h)

    # --- LEFT: Audit result table (same shape as the single-audit report) ---
    elements = vda_result.get("elements") or []
    process_elements = []
    for el in elements:
        element_code = str(el.get("element") or "").strip()
        if not element_code:
            continue
        idx = el.get("display_score")
        eg = el.get("eg_percent")
        if eg is None:
            ch_rating, eg_display = "n.e.", "n.e."
        else:
            eg_num = float(eg)
            eg_display = f"{eg_num:.0f}%"
            ch_rating = "A" if eg_num >= 90 else "B" if eg_num >= 80 else "C"
        process_elements.append(
            (element_code, "n.e." if idx is None else f"{float(idx):.1f}", eg_display, ch_rating)
        )
    while len(process_elements) < 4:
        process_elements.append(("n.e.", "n.e.", "n.e.", "n.e."))

    audit_result_style = ParagraphStyle(
        "AuditResult", fontName="Helvetica-Bold", fontSize=7, leading=8, alignment=TA_LEFT, wordWrap="CJK"
    )
    t1_data = [
        ["Audit result", "", "", ""],
        ["Evaluated process element", "Evaluation Index", "EG [%]", "Rating"],
        [
            Paragraph(str(questionnaire_name), audit_result_style),
            "",
            _fmt_pct(total_eg),
            total_rating,
        ],
        ["Evaluated product group", "", "", ""],
    ]
    for elem in process_elements:
        t1_data.append(list(elem))

    t1 = Table(t1_data, colWidths=[left_w * 0.4, left_w * 0.25, left_w * 0.2, left_w * 0.15])
    t1.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 0), (3, 0)),
                ("SPAN", (0, 3), (3, 3)),
                ("BACKGROUND", (0, 0), (3, 0), DARK_GREEN),
                ("TEXTCOLOR", (0, 0), (3, 0), WHITE),
                ("GRID", (0, 0), (-1, -1), 0.5, BLACK),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("ALIGN", (0, 2), (0, 2), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("FONTNAME", (0, 0), (3, 1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    t1_w, t1_h = t1.wrap(left_w, page_height)
    t1.drawOn(c, ml, curr_y - t1_h)

    curr_y -= (t1_h + 10)
    c.setFont("Helvetica", 6)
    c.drawString(
        ml,
        curr_y,
        "Classification scale: A = 90 - 100% quality capable; B = 80 - < 90% conditionally quality capable; C = 0 - < 80% not quality capable",
    )

    # --- "Consolidated Audits" table (replaces Last Audit Results slot) ---
    curr_y -= 40
    t2_data = [["Consolidated Audits", "", "", ""], ["Audit No.", "Date", "EG [%]", "Rating"]]
    for a in audits_meta:
        t2_data.append(
            [a["audit_number"], a.get("audit_date", "N/A"), f"{a.get('total_score', 0):.0f}%", str(a.get("result_class") or "n.e.")]
        )
    t2 = Table(t2_data, colWidths=[left_w * 0.3, left_w * 0.25, left_w * 0.2, left_w * 0.25], rowHeights=14)
    t2.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 0), (3, 0)),
                ("BACKGROUND", (0, 0), (3, 0), DARK_GREEN),
                ("TEXTCOLOR", (0, 0), (3, 0), WHITE),
                ("GRID", (0, 0), (-1, -1), 0.5, BLACK),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("FONTSIZE", (0, 0), (-1, -1), 6.5),
            ]
        )
    )
    t2_w, t2_h = t2.wrap(left_w, page_height)
    t2.drawOn(c, ml, curr_y - t2_h)

    # --- Auditors table (replaces the single Audit team slot) ---
    curr_y -= (t2_h + 25)
    t3_data = [["Audit team (consolidated):", "Audit No.", "Date"]]
    for a in audits_meta:
        t3_data.append([a.get("auditor", "N/A"), a["audit_number"], a.get("audit_date", "N/A")])
    t3 = Table(t3_data, colWidths=[left_w * 0.4, left_w * 0.3, left_w * 0.3], rowHeights=14)
    t3.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (2, 0), DARK_GREEN),
                ("TEXTCOLOR", (0, 0), (2, 0), WHITE),
                ("GRID", (0, 0), (-1, -1), 0.5, BLACK),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("FONTSIZE", (0, 0), (-1, -1), 6.5),
            ]
        )
    )
    t3_w, t3_h = t3.wrap(left_w, page_height)
    t3.drawOn(c, ml, curr_y - t3_h)

    # ========= PAGE(S): Per-Audit Summary, Findings and Conclusion ========
    # Each source audit's own Summary / Strengths / Opportunities /
    # Conclusion / Further action / Schedule of action plan, kept in its
    # own labeled block -- one audit's narrative never overwrites another's.
    c.showPage()
    page_width, page_height = landscape(A4)
    curr_y = page_height - 30
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(30, curr_y, "Per-Audit Summary, Findings and Conclusion")
    curr_y -= 25

    narrative_normal = ParagraphStyle("NarrNormal", fontName="Helvetica", fontSize=8, leading=10.5)
    narrative_bold = ParagraphStyle("NarrBold", fontName="Helvetica-Bold", fontSize=8, leading=10.5)
    narrative_header = ParagraphStyle(
        "NarrHeader", fontName="Helvetica-Bold", fontSize=9, textColor=WHITE, leading=11
    )
    narrative_width = page_width - 60

    for a in audits_meta:
        a_vda = a.get("vda_result") or {}
        a_eg = (a_vda.get("total") or {}).get("eg_percent")
        eg_for_conclusion = a_eg if a_eg is not None else a.get("total_score")
        rating = _rating_for_score(eg_for_conclusion, a.get("result_class"))
        conclusion_text = (
            f"Audit result {float(eg_for_conclusion):.0f}% rated {rating}."
            if eg_for_conclusion is not None
            else f"Audit result n.e., rated {rating}."
        )

        block_data = [
            [
                Paragraph(
                    f"Audit {a['audit_number']} — {a.get('plant', 'N/A')} — {a.get('audit_date', 'N/A')}",
                    narrative_header,
                )
            ],
            [Paragraph("Summary of the audit carried out", narrative_bold)],
            [Paragraph(_fmt_field(a.get("summary")), narrative_normal)],
            [Paragraph("Strengths", narrative_bold)],
            [Paragraph(_fmt_field(a.get("strong_points")), narrative_normal)],
            [Paragraph("Opportunities for Improvement", narrative_bold)],
            [Paragraph(_fmt_field(a.get("weak_points")), narrative_normal)],
            [Paragraph("Conclusion", narrative_bold)],
            [Paragraph(conclusion_text, narrative_normal)],
            [Paragraph("Further action", narrative_bold)],
            [
                Paragraph(
                    "Action plan should be delivered to Mahle 10 working days after receiving this file.",
                    narrative_normal,
                )
            ],
            [Paragraph("Schedule of action plan", narrative_bold)],
            [
                Paragraph(
                    f"Confirmation of measures: {_fmt_field(a.get('confirmation_date'))}"
                    f"&nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp;"
                    f"Effectiveness check: {_fmt_field(a.get('effectiveness_date'))}",
                    narrative_normal,
                )
            ],
        ]

        bt = Table(block_data, colWidths=[narrative_width])
        bt.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, 0), DARK_GREEN),
                    ("GRID", (0, 0), (-1, -1), 0.5, BLACK),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        bt_w, bt_h = bt.wrap(narrative_width, page_height)

        if curr_y - bt_h < 40:
            c.showPage()
            page_width, page_height = landscape(A4)
            c.setFillColor(colors.black)
            c.setFont("Helvetica-Bold", 14)
            c.drawString(30, page_height - 30, "Per-Audit Summary, Findings and Conclusion (cont.)")
            curr_y = page_height - 55

        bt.drawOn(c, 30, curr_y - bt_h)
        curr_y -= (bt_h + 16)

    # ========= PAGE(S): Per-Audit Detailed Evaluation Matrix ==============
    # Each source audit's own element-level ratings (Answered/Total,
    # Achieved/Max, EG%, Display A/B/C), independent of the merged/virtual
    # audit matrix rendered further below.
    c.showPage()
    page_width, page_height = landscape(A4)
    curr_y = page_height - 30
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(30, curr_y, "Per-Audit Detailed Evaluation Matrix")
    curr_y -= 25

    matrix_header_style = ParagraphStyle(
        "MatrixHeader", fontName="Helvetica-Bold", fontSize=9, textColor=WHITE, leading=11
    )
    matrix_width = 482

    for a in audits_meta:
        a_vda = a.get("vda_result") or {}
        a_elements = a_vda.get("elements") or []
        a_total = a_vda.get("total") or {}
        a_eg = a_total.get("eg_percent")
        a_rating = a_total.get("final_rating") or _rating_for_score(a_eg, a.get("result_class"))

        table_rows = [["Element", "Answered", "Total", "Achieved", "Max", "EG %", "Display"]]
        if a_elements:
            for el in a_elements:
                table_rows.append(
                    [
                        str(el.get("element", "")),
                        str(el.get("answered", 0)),
                        str(el.get("total", 0)),
                        str(el.get("achieved_points", 0)),
                        str(el.get("max_points", 0)),
                        _fmt_pct(el.get("eg_percent")),
                        _fmt_display(el.get("display_score")),
                    ]
                )
            table_rows.append(
                [
                    "TOTAL", "", "",
                    str(a_total.get("achieved_points", 0)),
                    str(a_total.get("max_points", 0)),
                    _fmt_pct(a_eg),
                    _fmt_display(a_total.get("display_score")),
                ]
            )
        else:
            table_rows.append(["n.e.", "n.e.", "n.e.", "n.e.", "n.e.", "n.e.", "n.e."])

        title = Table(
            [
                [
                    Paragraph(
                        f"Audit {a['audit_number']} — EG {_fmt_pct(a_eg)} — Rating {a_rating}",
                        matrix_header_style,
                    )
                ]
            ],
            colWidths=[matrix_width],
        )
        title.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, 0), DARK_GREEN),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        title_w, title_h = title.wrap(matrix_width, page_height)

        style_cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E7D52")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 7.5),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#7C8A96")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTSIZE", (0, 1), (-1, -1), 7.5),
        ]
        if a_elements:
            style_cmds += [
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F8FAFC")]),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EAF4EE")),
            ]
        dt = Table(table_rows, colWidths=[84, 68, 58, 72, 72, 64, 64], rowHeights=18)
        dt.setStyle(TableStyle(style_cmds))
        dt_w, dt_h = dt.wrap(matrix_width, page_height)

        block_h = title_h + dt_h + 14

        if curr_y - block_h < 40:
            c.showPage()
            page_width, page_height = landscape(A4)
            c.setFillColor(colors.black)
            c.setFont("Helvetica-Bold", 14)
            c.drawString(30, page_height - 30, "Per-Audit Detailed Evaluation Matrix (cont.)")
            curr_y = page_height - 55

        title.drawOn(c, 30, curr_y - title_h)
        dt.drawOn(c, 30, curr_y - title_h - dt_h)
        curr_y -= block_h

    # ================= PAGE: Consolidated Detailed Evaluation Matrix ======
    c.showPage()
    page_width, page_height = landscape(A4)

    p6_subgroups = vda_result.get("ep6_subgroups") or {}
    p3_p4_process_types = vda_result.get("p3_p4_process_types") or {}
    downgrade_reasons = vda_result.get("downgrade_reasons") or []

    def draw_header_band(y_top):
        c.setFillColor(colors.HexColor("#F3F8F5"))
        c.rect(24, y_top - 34, page_width - 48, 28, fill=1, stroke=0)
        c.setFillColor(DARK_GREEN)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(30, y_top - 20, "VDA 6.3 Detailed Evaluation Matrix (Consolidated)")
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 8.5)
        audits_label = ", ".join(audit_numbers)
        if len(audits_label) > 60:
            audits_label = audits_label[:57] + "..."
        c.drawString(30, y_top - 42, f"Audits: {audits_label}")
        c.drawString(390, y_top - 42, f"Plant: {plant_label}")
        c.drawRightString(page_width - 30, y_top - 42, f"Class: {total_rating}")

    def draw_total_summary(x, y_top, width, height):
        c.setFillColor(colors.HexColor("#F8FAFC"))
        c.roundRect(x, y_top - height, width, height, 8, fill=1, stroke=0)
        c.setStrokeColor(colors.HexColor("#C7D2E0"))
        c.roundRect(x, y_top - height, width, height, 8, fill=0, stroke=1)
        c.setFillColor(DARK_GREEN)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x + 12, y_top - 18, "Overall Compliance")
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 8)
        c.drawString(x + 12, y_top - 34, "Achieved / Max")
        c.drawString(x + 12, y_top - 48, "EG [%]")
        c.drawString(x + 12, y_top - 62, "Display / Rating")
        c.setFont("Helvetica-Bold", 11)
        c.drawRightString(x + width - 12, y_top - 34, f"{total.get('achieved_points', 0)} / {total.get('max_points', 0)}")
        c.drawRightString(x + width - 12, y_top - 48, _fmt_pct(total_eg))
        c.drawRightString(x + width - 12, y_top - 62, f"{_fmt_display(total.get('display_score'))} / {total_rating}")

    def build_elements_table():
        table_data = [["Element", "Answered", "Total", "Achieved", "Max", "EG %", "Display"]]
        for el in elements:
            table_data.append(
                [
                    str(el.get("element", "")),
                    str(el.get("answered", 0)),
                    str(el.get("total", 0)),
                    str(el.get("achieved_points", 0)),
                    str(el.get("max_points", 0)),
                    _fmt_pct(el.get("eg_percent")),
                    _fmt_display(el.get("display_score")),
                ]
            )
        table_data.append(
            [
                "TOTAL", "", "",
                str(total.get("achieved_points", 0)),
                str(total.get("max_points", 0)),
                _fmt_pct(total_eg),
                _fmt_display(total.get("display_score")),
            ]
        )
        return table_data

    def draw_matrix_table(x, y_top, width):
        table_data = build_elements_table()
        dt = Table(table_data, colWidths=[84, 68, 58, 72, 72, 64, 64], rowHeights=20)
        dt.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), DARK_GREEN),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 8),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#7C8A96")),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F8FAFC")]),
                    ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                    ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EAF4EE")),
                ]
            )
        )
        tw, th = dt.wrap(width, page_height)
        dt.drawOn(c, x, y_top - th)
        return th

    def draw_detail_box(x, y_top, width, title, subtitle, rows):
        height = 26 + (len(rows) * 16) + 12
        c.setFillColor(colors.white)
        c.roundRect(x, y_top - height, width, height, 7, fill=1, stroke=0)
        c.setStrokeColor(colors.HexColor("#C7D2E0"))
        c.roundRect(x, y_top - height, width, height, 7, fill=0, stroke=1)
        c.setFillColor(DARK_GREEN)
        c.roundRect(x, y_top - 24, width, 20, 7, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x + 8, y_top - 17, title)
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 7.5)
        c.drawString(x + 8, y_top - 34, subtitle)
        row_y = y_top - 50
        for label, value in rows:
            c.setFont("Helvetica", 7.5)
            c.drawString(x + 8, row_y, label)
            c.setFont("Helvetica-Bold", 7.5)
            c.drawRightString(x + width - 8, row_y, value)
            c.setStrokeColor(colors.HexColor("#E2E8F0"))
            c.line(x + 8, row_y - 5, x + width - 8, row_y - 5)
            row_y -= 16
        return height

    def element_by_code(code):
        for el in elements:
            if str(el.get("element")) == code:
                return el
        return {}

    def detail_rows_for_element(code):
        el = element_by_code(code)
        return [
            ("Answered / Total", f"{el.get('answered', 0)} / {el.get('total', 0)}"),
            ("Minimum 2/3", str(el.get("min_required_23", 0))),
            ("Rule met", "Yes" if el.get("rule_23_met") else "No"),
            ("Achieved / Max", f"{el.get('achieved_points', 0)} / {el.get('max_points', 0)}"),
            ("EG / Display", f"{_fmt_pct(el.get('eg_percent'))} / {_fmt_display(el.get('display_score'))}"),
        ]

    def detail_rows_for_process_map(proc_map):
        ordered_keys = ["product", "process_support", "unspecified"]
        rows = []
        for key in ordered_keys:
            info = proc_map.get(key)
            if not info:
                continue
            label = {"product": "Product", "process_support": "Process", "unspecified": "Unspecified"}[key]
            rows.append((label, f"{info.get('achieved_points', 0)} pts / {info.get('answered', 0)} ans."))
        return rows or [("Breakdown", "n.e.")]

    def detail_rows_for_subgroups(subgroups):
        ordered = ["6.1", "6.2", "6.3", "6.4", "6.5", "6.6"]
        rows = []
        for key in ordered:
            info = subgroups.get(key)
            if not info:
                continue
            rows.append((key, f"{_fmt_pct(info.get('eg_percent'))} / {info.get('answered', 0)} of {info.get('total', 0)}"))
        return rows or [("Subgroups", "n.e.")]

    def draw_downgrade_box(x, y_top, width):
        has_reasons = bool(downgrade_reasons)
        height = 92 if has_reasons else 52
        c.setFillColor(colors.HexColor("#FFF7ED"))
        c.roundRect(x, y_top - height, width, height, 7, fill=1, stroke=0)
        c.setStrokeColor(colors.HexColor("#FDBA74"))
        c.roundRect(x, y_top - height, width, height, 7, fill=0, stroke=1)
        c.setFillColor(colors.HexColor("#9A3412"))
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x + 10, y_top - 16, "Downgrade Rules / Findings")
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 7.5)
        if has_reasons:
            row_y = y_top - 32
            for reason in downgrade_reasons[:4]:
                c.drawString(x + 10, row_y, f"- {reason.get('question_code', 'N/A')}: {reason.get('message', '')}")
                row_y -= 14
        else:
            c.drawString(x + 10, y_top - 34, "No downgrade rule triggered across the merged audits.")
        if has_reasons:
            c.drawString(x + 10, y_top - height + 16, "At least 2/3 of the questions must be answered for each evaluated element.")
        return height

    draw_header_band(page_height - 18)
    draw_total_summary(page_width - 240, page_height - 64, 210, 76)
    table_height = draw_matrix_table(30, page_height - 88, page_width - 300)

    detail_top = page_height - 108 - table_height
    left_x, mid_x, right_x = 30, 270, 510
    box_w = 220

    p3_rows = detail_rows_for_process_map(p3_p4_process_types.get("P3", {}))
    p4_rows = detail_rows_for_process_map(p3_p4_process_types.get("P4", {}))
    p6_rows = detail_rows_for_subgroups(p6_subgroups)

    draw_detail_box(left_x, detail_top, box_w, "P2 Project management", "Element compliance overview", detail_rows_for_element("P2"))
    draw_detail_box(mid_x, detail_top, box_w, "P3 Planning product/process development", "Product and process split", p3_rows)
    draw_detail_box(right_x, detail_top, box_w, "P4 Implementation of product/process development", "Product and process split", p4_rows)

    second_row_top = detail_top - 128
    draw_detail_box(left_x, second_row_top, box_w, "P5 Supplier management", "Element compliance overview", detail_rows_for_element("P5"))
    draw_detail_box(mid_x, second_row_top, box_w, "P6 Process analysis / production", "Subgroup overview", p6_rows)
    draw_detail_box(right_x, second_row_top, box_w, "P7 Customer care / service", "Element compliance overview", detail_rows_for_element("P7"))

    draw_downgrade_box(30, second_row_top - 144, 460)

    summary_x = 520
    summary_y = second_row_top - 144
    c.setFillColor(colors.HexColor("#F8FAFC"))
    c.roundRect(summary_x, summary_y - 92, 260, 92, 7, fill=1, stroke=0)
    c.setStrokeColor(colors.HexColor("#C7D2E0"))
    c.roundRect(summary_x, summary_y - 92, 260, 92, 7, fill=0, stroke=1)
    c.setFillColor(DARK_GREEN)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(summary_x + 10, summary_y - 16, "Overall Compliance EG")
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 8)
    c.drawString(summary_x + 10, summary_y - 34, "Total points awarded")
    c.drawRightString(summary_x + 248, summary_y - 34, str(total.get("achieved_points", 0)))
    c.drawString(summary_x + 10, summary_y - 50, "Total possible points")
    c.drawRightString(summary_x + 248, summary_y - 50, str(total.get("max_points", 0)))
    c.drawString(summary_x + 10, summary_y - 66, "EG [%] / Rating")
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(summary_x + 248, summary_y - 66, f"{_fmt_pct(total_eg)} / {total_rating}")
    c.setFont("Helvetica", 7.5)
    c.drawString(summary_x + 10, summary_y - 82, f"Consolidated from {len(audits_meta)} audits.")

    # ================= PAGE 3: Action plan with defined immediate action =================
    c.showPage()
    page_width, page_height = landscape(A4)

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(30, page_height - 30, "Action plan with defined immediate action (Consolidated)")

    c.setFont("Helvetica-Bold", 9)
    c.drawString(30, page_height - 52, "Plant:")
    c.drawString(30, page_height - 68, "Audits:")
    c.drawString(page_width - 220, page_height - 52, "Questionnaire:")
    c.drawString(page_width - 220, page_height - 68, "Date range:")

    c.setFont("Helvetica", 9)
    c.drawString(95, page_height - 52, plant_label)
    audits_line = ", ".join(audit_numbers)
    if len(audits_line) > 60:
        audits_line = audits_line[:57] + "..."
    c.drawString(95, page_height - 68, audits_line)
    c.drawString(page_width - 130, page_height - 52, str(questionnaire_name)[:24])
    c.drawString(page_width - 130, page_height - 68, date_range)

    grouped: Dict[str, List[dict]] = {}
    for row in action_plan_rows:
        grouped.setdefault(row.get("element") or "Unclassified", []).append(row)

    def normalize_reference_label(value: str) -> str:
        v = (value or "").strip().lower()
        if "product" in v:
            return "Product"
        if "process" in v:
            return "Process"
        return ""

    action_header_cell_style = ParagraphStyle(
        "ActionHeaderCell", fontName="Helvetica-Bold", fontSize=6.5, leading=8, textColor=colors.white
    )
    action_cell_style = ParagraphStyle("ActionCell", fontName="Helvetica", fontSize=6.5, leading=8)

    table_data = [
        [
            "Filled in by the auditor in the questionnaire", "", "", "", "", "",
            "Filled in by the audited area", "", "", "", "",
        ],
        [
            Paragraph(label, action_header_cell_style)
            for label in (
                "Question No.", "Audit", "Reference", "Audit results", "Points", "Immediate action",
                "Reason(s)", "Measure(s)", "Deadline", "Responsibility", "Effectivity",
            )
        ],
    ]

    for element in sorted(grouped.keys()):
        section_label = f"{element} {VDA_ELEMENT_LABELS.get(element, '')}".strip()
        table_data.append([section_label] + [""] * 10)
        for row in grouped[element]:
            corrective_actions = row.get("corrective_action") or []
            has_immediate_action = any(ca.get("action_type") == "immediate" for ca in corrective_actions)
            q_no = row.get("question_code") or "N/A"
            reference = normalize_reference_label(row.get("chapter"))
            findings = row.get("finding_text") or ""
            value = row.get("value")
            points = str(value) if value is not None else "n.e."
            immediate = "Yes" if has_immediate_action else "n.e."
            table_data.append(
                [
                    Paragraph(q_no, action_cell_style),
                    Paragraph(row.get("audit_number", ""), action_cell_style),
                    Paragraph(reference, action_cell_style),
                    Paragraph(findings, action_cell_style),
                    points,
                    Paragraph(immediate, action_cell_style),
                    "", "", "", "", "",
                ]
            )

    if len(table_data) == 2:
        table_data.append(["N/A", "", "", "No answered questions were found across the merged audits.", "", "", "", "", "", "", ""])

    action_table = Table(
        table_data,
        colWidths=[50, 78, 42, 128, 30, 62, 80, 80, 50, 55, 50],
        repeatRows=2,
    )
    action_table.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 0), (5, 0)),
                ("SPAN", (6, 0), (10, 0)),
                ("BACKGROUND", (0, 0), (5, 0), colors.HexColor("#D9D9D9")),
                ("BACKGROUND", (6, 0), (10, 0), colors.HexColor("#D9D9D9")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8.5),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("BACKGROUND", (0, 1), (-1, 1), DARK_GREEN),
                ("TEXTCOLOR", (0, 1), (-1, 1), colors.white),
                ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 1), (-1, 1), 7),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.black),
                ("ALIGN", (4, 2), (5, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("FONTSIZE", (0, 2), (-1, -1), 6.5),
            ]
        )
    )

    for i, row in enumerate(table_data[2:], start=2):
        if row[2] == "" and row[3] == "" and row[4] == "":
            action_table.setStyle(
                TableStyle(
                    [
                        ("SPAN", (0, i), (-1, i)),
                        ("BACKGROUND", (0, i), (-1, i), colors.HexColor("#808080")),
                        ("TEXTCOLOR", (0, i), (-1, i), colors.white),
                        ("FONTNAME", (0, i), (-1, i), "Helvetica-Bold"),
                    ]
                )
            )

    tw, th = action_table.wrap(page_width - 60, page_height - 160)
    action_table.drawOn(c, 30, max(70, page_height - 110 - th))

    c.setFont("Helvetica", 8.5)
    c.setFillColor(colors.black)
    c.drawString(30, 22, "Audit VDA6.3 (1) — Consolidated")
    c.drawRightString(page_width - 30, 22, "Copyright VDA QMC 2016")

    c.save()
    buffer.seek(0)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Findings-based consolidation (every non-VDA report profile)
# ---------------------------------------------------------------------------
#
# IATF NC, IATF Plant Manager, standalone P1 Potential Analysis and standard
# questionnaires don't map onto the VDA P2-P7 elements, so re-scoring them
# with compute_vda_results yields an empty 0/0 matrix. Instead they get a
# findings report: each source audit keeps its own score, and their findings
# are merged into one list grouped by theme (IATF clause / question chapter).

IATF_CHAPTER_TITLES = {
    "4": "Context of the organization",
    "5": "Leadership",
    "6": "Planning",
    "7": "Support",
    "8": "Operation",
    "9": "Performance evaluation",
    "10": "Improvement",
}

NC_CLASSIFICATIONS = ("Major", "Minor", "Improvement")
STATUS_LABELS = {"fail": "Fail", "improve": "Improve"}

# Placeholder values get_audit_data_for_report / migrated audits use for
# "nothing written" -- not worth a narrative row in the report.
_EMPTY_NARRATIVES = {
    "", "na", "n/a", "n.e.", "none", "-",
    "no strong points documented.", "no weak points documented.",
}


def _escape(value) -> str:
    text = str(value) if value is not None else ""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return text.replace("\r\n", "\n").replace("\n", "<br/>")


def _has_narrative(value) -> bool:
    return str(value or "").strip().lower() not in _EMPTY_NARRATIVES


def _corrective_car(question: dict):
    cars = question.get("corrective_action") or []
    return next((c for c in cars if c.get("action_type") == "corrective"), None) or (
        cars[0] if cars else None
    )


def _theme_for(question: dict, report_profile: str):
    """Return (sort_key, label) of the theme a finding is grouped under."""
    if report_profile == "IATF_NC":
        clause = str(question.get("standard_paragraph") or "").strip()
        head = clause.split(" ")[0].split(".")[0]
        if head.isdigit():
            title = IATF_CHAPTER_TITLES.get(head)
            label = f"Clause {head}" + (f" - {title}" if title else "")
            return (0, int(head), ""), label
        return (1, 0, clause.lower()), clause or "Other"

    chapter = str(question.get("chapter") or "").strip()
    if not chapter or chapter in ("Unknown", "N/A"):
        return (2, 0, ""), "Unclassified"
    return (0, 0, chapter.lower()), chapter


def build_consolidated_findings(audits_data: List[dict], report_profile: str) -> List[dict]:
    """Flatten the findings of several get_audit_data_for_report() payloads.

    IATF NC audits contribute every Major/Minor/Improvement; other profiles
    contribute their failed / to-improve answers. Passed answers and Strong
    Points are not findings and are left out (Strong Points are counted in
    the per-audit table instead).
    """
    rows = []
    for audit_data in audits_data:
        for question in audit_data.get("detailed_questions") or []:
            classification = question.get("classification")
            if report_profile == "IATF_NC":
                if classification not in NC_CLASSIFICATIONS:
                    continue
                severity = classification
            else:
                if question.get("status") not in STATUS_LABELS:
                    continue
                severity = STATUS_LABELS[question["status"]]

            car = _corrective_car(question)
            question_text = str(question.get("question_text") or "").strip()
            finding_text = str(question.get("finding_text") or "").strip()
            # IATF NC findings are free-form: the observed non-conformity is
            # written on the CAR (reason_why), not on the answer.
            observed = str((car or {}).get("reason_why") or "").strip()
            if report_profile == "IATF_NC":
                description = observed or finding_text or (
                    "" if question_text == "No description" else question_text
                )
            else:
                description = question_text
                if finding_text:
                    description = f"{question_text}\n{finding_text}" if question_text else finding_text

            reference = (
                question.get("standard_paragraph")
                if report_profile == "IATF_NC"
                else question.get("question_code") or question.get("chapter")
            )
            theme_key, theme_label = _theme_for(question, report_profile)
            rows.append(
                {
                    "audit_number": audit_data.get("audit_number") or "N/A",
                    "theme_key": theme_key,
                    "theme": theme_label,
                    "reference": str(reference or "").strip() or "N/A",
                    "process": str(question.get("process") or "").strip(),
                    "description": description or "No description recorded.",
                    "severity": severity,
                    "car_status": (car or {}).get("status") or "",
                    "due_date": (car or {}).get("due_date") or "",
                }
            )
    return rows


def generate_consolidated_findings_report(
    audits_data: List[dict],
    findings: List[dict],
    report_profile: str,
) -> bytes:
    """Render the findings-based consolidated report to PDF bytes.

    audits_data: get_audit_data_for_report() payloads, in the auditor's
        selection order.
    findings: rows from build_consolidated_findings().
    report_profile: shared profile of the audits (IATF_NC, IATF_PM, ...).
    """
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import PageBreak, SimpleDocTemplate, Spacer

    is_nc = report_profile == "IATF_NC"
    severities = list(NC_CLASSIFICATIONS) if is_nc else list(STATUS_LABELS.values())

    audit_numbers = [a.get("audit_number") or "N/A" for a in audits_data]
    plant_label = ", ".join(sorted({str(a.get("plant") or "N/A") for a in audits_data}))
    questionnaire_name = next(
        (a.get("questionnaire_name") for a in audits_data if a.get("questionnaire_name")),
        "N/A",
    )
    dates = sorted(d for d in (a.get("audit_date") for a in audits_data) if d and d != "N/A")
    date_range = f"{dates[0]} - {dates[-1]}" if dates else "N/A"

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ConsTitle", parent=styles["Heading1"], fontSize=16, textColor=DARK_GREEN, spaceAfter=4
    )
    section_style = ParagraphStyle(
        "ConsSection", parent=styles["Heading2"], fontSize=12, textColor=DARK_GREEN,
        spaceBefore=10, spaceAfter=6,
    )
    body = ParagraphStyle("ConsBody", parent=styles["Normal"], fontSize=8.5, leading=11)
    cell = ParagraphStyle("ConsCell", parent=body, fontSize=7.5, leading=9.5, alignment=TA_LEFT)
    head = ParagraphStyle("ConsHead", parent=cell, fontName="Helvetica-Bold", textColor=WHITE)

    def p(value, style=cell):
        return Paragraph(_escape(value), style)

    def table(data, col_widths, header_rows=1, extra_styles=()):
        t = Table(data, colWidths=col_widths, repeatRows=header_rows)
        t.setStyle(
            TableStyle(
                [
                    *([("BACKGROUND", (0, 0), (-1, header_rows - 1), DARK_GREEN)] if header_rows else []),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9ca3af")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    *extra_styles,
                ]
            )
        )
        return t

    story = [
        Paragraph("Consolidated Audit Report", title_style),
        Paragraph(
            _escape(f"{questionnaire_name} - {len(audits_data)} audits merged: {', '.join(audit_numbers)}"),
            body,
        ),
        Spacer(1, 8),
        table(
            [
                [p("Plant", head), p(plant_label), p("Questionnaire", head), p(questionnaire_name)],
                [p("Date range", head), p(date_range), p("Audits merged", head), p(len(audits_data))],
            ],
            [90, 290, 90, 290],
            header_rows=0,
            extra_styles=[
                ("BACKGROUND", (0, 0), (0, -1), DARK_GREEN),
                ("BACKGROUND", (2, 0), (2, -1), DARK_GREEN),
            ],
        ),
    ]

    # ---- Per-audit overview: each audit keeps its own score ------------------
    story.append(Paragraph("Audits included", section_style))
    count_columns = severities + (["Strong Point"] if is_nc else [])
    overview = [
        [p(h, head) for h in ["Audit No.", "Date", "Auditor", "Score", "Rating", *count_columns, "Findings"]]
    ]
    totals = {key: 0 for key in count_columns}
    for audit_data in audits_data:
        number = audit_data.get("audit_number") or "N/A"
        own = [f for f in findings if f["audit_number"] == number]
        counts = {s: sum(1 for f in own if f["severity"] == s) for s in severities}
        if is_nc:
            counts["Strong Point"] = sum(
                1 for q in audit_data.get("detailed_questions") or []
                if q.get("classification") == "Strong Point"
            )
        for key in count_columns:
            totals[key] += counts[key]
        score = audit_data.get("total_score")
        overview.append(
            [
                p(number),
                p(audit_data.get("audit_date") or "N/A"),
                p(audit_data.get("auditor") or "N/A"),
                p(f"{float(score):.0f}%" if score is not None else "n.e."),
                p(audit_data.get("result_class") or "n.e."),
                *[p(counts[key]) for key in count_columns],
                p(len(own)),
            ]
        )
    overview.append(
        [p("Total", head), p(""), p(""), p(""), p(""),
         *[p(totals[key], head) for key in count_columns], p(len(findings), head)]
    )
    story.append(
        table(
            overview,
            [80, 95, 120, 50, 50, *[62] * len(count_columns), 55],
            extra_styles=[("BACKGROUND", (0, -1), (-1, -1), DARK_GREEN)],
        )
    )

    # ---- Per-audit statements (only what auditors actually wrote) -----------
    narrative_rows = []
    for audit_data in audits_data:
        for label, key in (("Summary", "summary"), ("Strengths", "strong_points"),
                           ("Opportunities for improvement", "weak_points")):
            if _has_narrative(audit_data.get(key)):
                narrative_rows.append(
                    [p(audit_data.get("audit_number") or "N/A"), p(label), p(audit_data.get(key))]
                )
    if narrative_rows:
        story.append(Paragraph("Auditor statements", section_style))
        story.append(
            table([[p(h, head) for h in ["Audit No.", "Topic", "Statement"]], *narrative_rows],
                  [80, 140, 560])
        )

    # ---- Findings grouped by theme ------------------------------------------
    story.append(PageBreak())
    story.append(Paragraph("Consolidated findings by theme", section_style))
    if not findings:
        story.append(Paragraph("No findings were recorded across the selected audits.", body))
    else:
        severity_rank = {s: i for i, s in enumerate(severities)}
        audit_rank = {number: i for i, number in enumerate(audit_numbers)}
        ordered = sorted(
            findings,
            key=lambda f: (f["theme_key"], severity_rank.get(f["severity"], 99),
                           audit_rank.get(f["audit_number"], 99)),
        )
        headers = ["#", "Audit", "Clause" if is_nc else "Reference",
                   "Process" if is_nc else "Chapter",
                   "Non-conformity" if is_nc else "Question / finding",
                   "Classification" if is_nc else "Result", "CAR status", "Due date"]
        data = [[p(h, head) for h in headers]]
        theme_rows = []
        current_theme = None
        for index, finding in enumerate(ordered, 1):
            if finding["theme"] != current_theme:
                current_theme = finding["theme"]
                in_theme = sum(1 for f in ordered if f["theme"] == current_theme)
                theme_rows.append(len(data))
                data.append([p(f"{current_theme}  ({in_theme})", head), "", "", "", "", "", "", ""])
            data.append(
                [
                    p(index),
                    p(finding["audit_number"]),
                    p(finding["reference"]),
                    p(finding["process"] if is_nc else finding["theme"]),
                    p(finding["description"]),
                    p(finding["severity"]),
                    p(str(finding["car_status"]).replace("_", " ") or "-"),
                    p(finding["due_date"] or "-"),
                ]
            )
        theme_styles = []
        for row in theme_rows:
            theme_styles += [
                ("SPAN", (0, row), (-1, row)),
                ("BACKGROUND", (0, row), (-1, row), colors.HexColor("#4b5563")),
            ]
        story.append(table(data, [22, 58, 105, 105, 320, 62, 55, 55], extra_styles=theme_styles))

    def draw_footer(c, doc):
        width, _ = landscape(A4)
        c.saveState()
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.HexColor("#4b5563"))
        c.drawString(30, 18, f"Consolidated audit report - {questionnaire_name} - {plant_label}")
        c.drawRightString(width - 30, 18, f"Page {doc.page}")
        c.restoreState()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=30, rightMargin=30, topMargin=30, bottomMargin=36,
        title=f"Consolidated audit report - {', '.join(audit_numbers)}",
    )
    doc.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
    return buffer.getvalue()
