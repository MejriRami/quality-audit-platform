"""
IATF NC Report Generation Service
Generates professional PDF reports for IATF Non-Conformity audits
"""

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
    Image, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from datetime import datetime
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def create_iatf_nc_cover_page(story, audit_data, logo_path=None, styles=None):
    """
    Create cover page for IATF NC report
    """
    if styles is None:
        styles = getSampleStyleSheet()
    
    # Add logo at the top
    if logo_path and Path(logo_path).exists():
        try:
            logo = Image(logo_path, width=2*inch, height=0.8*inch)
            logo.hAlign = 'LEFT'
            story.append(logo)
            story.append(Spacer(1, 0.3*inch))
        except Exception as e:
            logger.warning(f"Could not load logo: {e}")
    
    # Title centered
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1e3a8a'),
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    title = Paragraph("Audit Report", title_style)
    story.append(title)
    story.append(Spacer(1, 0.5*inch))
    
    # Audit info table
    label_style = ParagraphStyle(
        'LabelStyle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.black,
        fontName='Helvetica-Bold'
    )
    
    value_style = ParagraphStyle(
        'ValueStyle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.black,
        fontName='Helvetica',
        alignment=TA_RIGHT
    )
    
    info_data = [
        [Paragraph("Plant", label_style), Paragraph(audit_data.get('plant', 'N/A'), value_style)],
        [Paragraph("Audit Number", label_style), Paragraph(audit_data.get('audit_number', 'N/A'), value_style)],
        [Paragraph("Audit start date", label_style), Paragraph(audit_data.get('audit_date', 'N/A'), value_style)],
        [Paragraph("Audit end date", label_style), Paragraph(audit_data.get('audit_end_date', 'N/A'), value_style)],
        [Paragraph("Auditors", label_style), Paragraph(audit_data.get('auditor', 'N/A'), value_style)],
        [Paragraph("Auditee", label_style), Paragraph(audit_data.get('auditees', 'N/A'), value_style)],
    ]
    
    info_table = Table(info_data, colWidths=[3*inch, 3.5*inch])
    info_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    
    story.append(info_table)
    story.append(PageBreak())


def create_iatf_nc_summary_page(story, audit_data, styles):
    """
    Create summary page listing all non-conformities in table format
    """
    # Page title
    title_style = ParagraphStyle(
        'PageTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#1e3a8a'),
        spaceAfter=20,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    story.append(Paragraph("Audit Report", title_style))
    story.append(Spacer(1, 0.3*inch))
    
    # Get NC data from detailed_questions
    detailed_questions = audit_data.get('detailed_questions', [])
    
    # Count by classification
    classification_counts = {
        'Major': 0,
        'Minor': 0,
        'Improvement': 0,
        'Strong Point': 0
    }
    
    nc_list = []
    for q in detailed_questions:
        classification = q.get('classification')
        if classification:
            classification_counts[classification] = classification_counts.get(classification, 0) + 1
            nc_list.append(q)
    
    # Summary counts table
    summary_data = [
        ['Classification', 'Count'],
        ['Major Non-Conformities', str(classification_counts.get('Major', 0))],
        ['Minor Non-Conformities', str(classification_counts.get('Minor', 0))],
        ['Improvements', str(classification_counts.get('Improvement', 0))],
        ['Strong Points', str(classification_counts.get('Strong Point', 0))],
        ['Total', str(len(nc_list))],
    ]
    
    summary_table = Table(summary_data, colWidths=[4*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f1f5f9')),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e1')),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('TOPPADDING', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e2e8f0')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ]))
    
    story.append(summary_table)
    story.append(Spacer(1, 0.4*inch))
    
    # NC List Table
    if not nc_list:
        story.append(Paragraph("No non-conformities recorded.", styles['Normal']))
        return
    
    # Header style
    header_style = ParagraphStyle(
        'HeaderStyle',
        parent=styles['Normal'],
        fontSize=8,
        fontName='Helvetica-Bold',
        textColor=colors.whitesmoke,
        alignment=TA_CENTER,
        leading=10
    )
    
    # Cell style
    cell_style = ParagraphStyle(
        'CellStyle',
        parent=styles['Normal'],
        fontSize=8,
        leading=10,
        alignment=TA_LEFT
    )
    
    # Create NC summary table
    table_data = [
        [
            Paragraph('NC<br/>no.', header_style),
            Paragraph('NC<br/>identification<br/>no.', header_style),
            Paragraph("Auditor's name", header_style),
            Paragraph('Standard', header_style),
            Paragraph('Standard<br/>clause', header_style),
            Paragraph('Nonconformity observed<br/>in process', header_style),
            Paragraph('Classification', header_style),
            Paragraph('Due date max.<br/>10 days', header_style),
        ]
    ]
    
    # Add NC rows
    for idx, nc in enumerate(nc_list, 1):
        # Extract data
        nc_number = str(idx)
        nc_id = nc.get('identifier', f'NC{idx}')
        nc_process=nc.get('process', f'NC{idx}')
        auditor = audit_data.get('auditor', 'N/A')
        standard = nc.get('standard', 'IATF 16949:2016')
        standard_clause = nc.get('standard_paragraph', 'N/A')
        classification = nc.get('classification', 'N/A').lower()
        
        # Get due date from the corrective (root-cause) CAR if one exists.
        # A finding can carry a linked immediate-action CAR too, but that one
        # has no due_date of its own (it runs on a 24h/48h SLA instead), so
        # this "Due date max. 10 days" column always reflects the corrective
        # row specifically.
        due_date = ''
        corrective_actions = nc.get('corrective_action') or []
        car = next((c for c in corrective_actions if c.get('action_type') == 'corrective'), None) \
            or (corrective_actions[0] if corrective_actions else None)
        if car:
            due_date = car.get('due_date', '')
            if due_date:
                try:
                    dt = datetime.fromisoformat(due_date)
                    due_date = dt.strftime('%d.%b.%Y')
                except:
                    pass

        nc_id = nc.get('identifier', f'NC{idx}')

        row = [
            Paragraph(nc_number, cell_style),
            Paragraph(nc_id, cell_style),
            Paragraph(auditor, cell_style),
            Paragraph(standard, cell_style),
            Paragraph(standard_clause, cell_style),
            Paragraph(nc_process, cell_style),

            Paragraph(classification, cell_style),
                        Paragraph(due_date, cell_style),

        ]
        
        table_data.append(row)
    
    # Column widths optimized for letter size
    col_widths = [
        0.4*inch,   # NC no
        0.7*inch,   # NC ID
        0.9*inch,   # Auditor
        1.0*inch,   # Standard
        0.7*inch,   # Clause
                1.7*inch,   # Observed NC

        0.8*inch,   # Classification
        0.8*inch,   # Due date
    ]
    
    nc_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    nc_table.setStyle(TableStyle([
        # Header
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        # Data rows
        ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('TOPPADDING', (0, 1), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
    ]))
    
    story.append(nc_table)
    story.append(PageBreak())


def create_iatf_nc_detail_pages(story, audit_data, styles):
    """
    Create detailed page for each non-conformity matching DQS format
    """
    detailed_questions = audit_data.get('detailed_questions', [])
    
    # Filter only NCs (those with classification)
    nc_list = [q for q in detailed_questions if q.get('classification')]
    
    if not nc_list:
        return
    
    for idx, nc in enumerate(nc_list, 1):
        # Section for each NC
        elements = []
        
        # Page title
        title_style = ParagraphStyle(
            'PageTitle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor('#1e3a8a'),
            spaceAfter=20,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )

        elements.append(Paragraph("Audit Report", title_style))
        elements.append(Spacer(1, 0.3*inch))
        
        # NC & actions header
        header_style = ParagraphStyle(
            'NCHeader',
            parent=styles['Heading3'],
            fontSize=12,
            textColor=colors.black,
            spaceAfter=5,
            fontName='Helvetica-Bold'
        )
        
        elements.append(Paragraph("NC & actions", header_style))
        elements.append(Paragraph(f"Nonconformity {idx}", styles['Normal']))
        elements.append(Paragraph("To be completed by the CB auditor", styles['Normal']))
        elements.append(Spacer(1, 0.15*inch))
        
        # NC Header section
        section_header_style = ParagraphStyle(
            'SectionHeader',
            parent=styles['Normal'],
            fontSize=10,
            fontName='Helvetica-Bold',
            spaceAfter=8,
        )
        
        elements.append(Paragraph("NC header", section_header_style))
        
        # Get data
        nc_id = nc.get('identifier', f'RT0{idx}')
        standard = 'IATF 16949:2016'
        classification = nc.get('classification', 'minor').lower()
        
        # Due date (from the corrective/root-cause row -- see comment on the
        # equivalent lookup above)
        due_date = ''
        corrective_actions = nc.get('corrective_action') or []
        car = next((c for c in corrective_actions if c.get('action_type') == 'corrective'), None) \
            or (corrective_actions[0] if corrective_actions else None)
        if car:
            due_date = car.get('due_date', '')
            if due_date:
                try:
                    dt = datetime.fromisoformat(due_date)
                    due_date = dt.strftime('%d.%b.%Y')
                except:
                    pass

        # Surface the linked immediate-action row, when this finding has one,
        # so the report doesn't silently drop it (previously only one CAR per
        # finding was ever fetched here).
        immediate_action = next(
            (c for c in corrective_actions if c.get('action_type') == 'immediate'), None
        )

        standard_clause = nc.get('standard_paragraph', 'N/A')
        nc_process=nc.get("process",'N/A')
        # Get the standard clause title/description if available
        # standard_clause_description = ""
        # if standard_clause != 'N/A':
        #     # You might want to have a lookup for standard clause descriptions
        #     # For now, using a generic description
        #     standard_clause_description = "Customer complaints and field failure test analysis"
        
        # Label and value style
        label_style = ParagraphStyle(
            'Label',
            parent=styles['Normal'],
            fontSize=9,
            fontName='Helvetica-Bold',
            textColor=colors.black,
        )
        
        value_style = ParagraphStyle(
            'Value',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.black,
        )
        
        # NC Header table data
        header_data = [
            [Paragraph("NC identification no.", label_style), Paragraph(nc_id, value_style)],
            [Paragraph("Standard", label_style), Paragraph(standard, value_style)],
            [Paragraph("Classification", label_style), Paragraph(classification, value_style)],
            [Paragraph("Due date max. 10 days", label_style), Paragraph(due_date, value_style)],
            [Paragraph("Nonconformity observed in process", label_style), Paragraph(nc_process, value_style)],
            [Paragraph("Standard clause", label_style),Paragraph(f"{standard_clause}<br/>", value_style)
            ],
        ]

        if immediate_action:
            closure_due_at = immediate_action.get('closure_due_at') or 'N/A'
            immediate_status = immediate_action.get('status', 'unknown')
            header_data.append([
                Paragraph("Immediate action (24h/48h)", label_style),
                Paragraph(f"Status: {immediate_status} &middot; Close by: {closure_due_at}", value_style),
            ])
        
        header_table = Table(header_data, colWidths=[2.2*inch, 4.8*inch])
        header_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f8f9fa')),
        ]))
        
        elements.append(header_table)
        elements.append(Spacer(1, 0.15*inch))
        
        # Requirement section (using findings from the NC)
        elements.append(Paragraph("Finding", section_header_style))
        
        # Get the requirement text - in IATF NC, this comes from findings
        requirement_text = nc.get('finding_text', '') or nc.get('note', '') or''


        elements.append(Paragraph(requirement_text, value_style))

        elements.append(Spacer(1, 0.15*inch))

        # Non-conformity statement (the "Observed Non-Conformity" text entered
        # by the auditor -- stored on the linked CorrectiveAction as
        # reason_why, distinct from the finding text above).
        non_conformity_text = (car.get('reason_why') if car else '') or ''
        if non_conformity_text:
            elements.append(Paragraph("Non-conformity", section_header_style))
            elements.append(Paragraph(non_conformity_text, value_style))
            elements.append(Spacer(1, 0.15*inch))
        
        # Keep together and add page break
        story.append(KeepTogether(elements))
        if idx < len(nc_list):
            story.append(PageBreak())


def generate_iatf_nc_report(audit_data, output_path, logo_path=None):
    """
    Generate IATF NC Management Report
    
    Args:
        audit_data: Dictionary containing audit and NC information
        output_path: Path where PDF should be saved
        logo_path: Optional path to company logo
        
    Returns:
        Path to generated PDF
    """
    # Ensure output directory exists
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create PDF document
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=0.75*inch,
        leftMargin=0.75*inch,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch,
        title=f"IATF NC Report - {audit_data.get('audit_number', 'N/A')}",
        author=audit_data.get('auditor', 'Audit System'),
    )
    
    story = []
    styles = getSampleStyleSheet()
    
    # Add custom styles
    styles.add(ParagraphStyle(
        name='Justify',
        parent=styles['Normal'],
        alignment=TA_JUSTIFY,
    ))
    
    # Create report sections
    create_iatf_nc_cover_page(story, audit_data, logo_path, styles)
    create_iatf_nc_summary_page(story, audit_data, styles)
    create_iatf_nc_detail_pages(story, audit_data, styles)
    
    # Build PDF
    doc.build(story)
    
    logger.info(f"IATF NC Report generated successfully: {output_path}")
    return output_path