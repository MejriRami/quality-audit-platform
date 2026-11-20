"""
Audit Report Generation Service
Generates professional PDF reports for audits with cover page and detailed content
"""

from typing import  Optional
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
    Image, 
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from datetime import datetime
from pathlib import Path
import os
import logging
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.path import Path as MplPath
import numpy as np
from collections import defaultdict
import tempfile

from app.services.iatf_system_nc_report_generator import generate_iatf_nc_report

logger = logging.getLogger(__name__)


def create_radar_chart(audit_data, output_path):
    """
    Create a radar chart showing KPI scores by chapter with weak areas highlighted
    Similar to the Monthly Plant Manager KPI Audit chart
    
    Args:
        audit_data: Dictionary containing audit information with detailed_questions
        output_path: Path where the chart image should be saved
        
    Returns:
        Path to the generated chart image, or None if chart cannot be created
    """
    detailed_questions = audit_data.get('detailed_questions', [])
    
    if not detailed_questions:
        logger.warning("No detailed questions available for radar chart")
        return None
    
    # Aggregate scores by chapter
    chapter_scores = defaultdict(list)
    for question in detailed_questions:
        if question.get('is_requirement'):
            continue  # finding rows, not separately scored questions
        chapter = question.get('chapter', 'Unknown')
        value = question.get('value')
        
        # Only include questions with valid numeric scores
        if value is not None:
            try:
                score = float(value)
                if 1 <= score <= 5:  # Validate score is in range
                    chapter_scores[chapter].append(score)
            except (ValueError, TypeError):
                continue
    
    if not chapter_scores:
        logger.warning("No valid chapter scores found for radar chart")
        return None
    
    # Calculate average score per chapter
    categories = []
    scores = []
    weak_areas = []  # Track which areas are weak (<=3)
    
    for chapter, values in sorted(chapter_scores.items()):
        avg_score = sum(values) / len(values)
        categories.append(chapter)
        scores.append(avg_score)
        weak_areas.append(avg_score <= 3)  # Mark as weak if score <= 3
    
    # Number of variables
    num_vars = len(categories)
    
    if num_vars == 0:
        logger.warning("No categories found for radar chart")
        return None
    
    # Compute angle for each axis
    angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()
    
    # Complete the circle
    scores += scores[:1]
    angles += angles[:1]
    
    # Create figure
    fig, ax = plt.subplots(figsize=(12, 10), subplot_kw=dict(projection='polar'))
    
    # Set figure background
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')
    
    # Draw the outer circle and grid
    ax.set_ylim(0, 5)
    ax.set_yticks([1, 2, 3, 4, 5])
    ax.set_yticklabels(['1', '2', '3', '4', '5'], fontsize=10, color='gray')
    ax.grid(True, linewidth=0.5, color='gray', alpha=0.3)
    
    # Plot the main scores (blue area)
    ax.plot(angles, scores, 'o-', linewidth=2, color='#4472C4', label='Score (1-5)')
    ax.fill(angles, scores, alpha=0.6, color='#4472C4')
    
    # Highlight weak areas (red overlay)
    # Create separate polygons for each weak area
    for i, is_weak in enumerate(weak_areas):
        if is_weak:
            # Create a triangle for this weak section
            weak_angles = [angles[i], 0, angles[i+1]]
            weak_scores = [scores[i], 0, scores[i+1]]
            
            ax.plot([angles[i], angles[i+1]], [scores[i], scores[i+1]], 
                   linewidth=2, color='#FF6B6B')
            ax.fill(weak_angles, weak_scores, alpha=0.5, color='#FF6B6B')
    
    # Set category labels
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, fontsize=11, weight='normal')
    
    # Add title
    plt.title('Monthly Plant Manager KPI Audit (Dynamic) — Weak Areas Highlighted', 
             size=16, weight='bold', pad=30)
    
    # Create custom legend
    blue_patch = mpatches.Patch(color='#4472C4', alpha=0.6, label='Score (1-5)')
    red_patch = mpatches.Patch(color='#FF6B6B', alpha=0.5, label='Weak (≤3)')
    ax.legend(handles=[blue_patch, red_patch], loc='upper right', 
             bbox_to_anchor=(1.3, 1.1), fontsize=10)
    
    # Adjust layout to prevent label cutoff
    plt.tight_layout()
    
    # Save the chart
    try:
        plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()
        logger.info(f"Radar chart created successfully: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Error saving radar chart: {e}")
        plt.close()
        return None


def create_cover_page(story, audit_data, logo_path=None, styles=None):
    """
    Create a professional cover page similar to the reference image
    
    Args:
        story: ReportLab story list to append elements to
        audit_data: Dictionary containing audit information
        logo_path: Path to the company logo
        styles: ReportLab styles
    """
    if styles is None:
        styles = getSampleStyleSheet()
    
    # Add logo at the top
    if logo_path and os.path.exists(logo_path):
        try:
            logo = Image(logo_path, width=2*inch, height=0.8*inch)
            logo.hAlign = 'LEFT'
            story.append(logo)
            story.append(Spacer(1, 0.3*inch))
        except Exception as e:
            print(f"Warning: Could not load logo: {e}")
    
    # Title style - centered, bold, larger - Northwind dark blue
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1e3a8a'),
        spaceAfter=6,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    # Subtitle style - centered, gray
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=14,
        textColor=colors.HexColor('#64748b'),
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName='Helvetica'
    )
    
    # Add title - "Audit Report"
    title_text = f"Audit Report N° {audit_data.get('audit_number', 'N/A')}"
    title = Paragraph(title_text, title_style)
    story.append(title)
    
    # Add subtitle if questionnaire name exists
    if audit_data.get('questionnaire_name'):
        subtitle = Paragraph(audit_data.get('questionnaire_name', ''), subtitle_style)
        story.append(subtitle)
    else:
        story.append(Spacer(1, 0.3*inch))
    
    # Add large centered logo/icon area (optional - can be removed)
    story.append(Spacer(1, 0.5*inch))
    
    # Create information table with labels and values
    info_data = []
    
    # Table label style
    label_style = ParagraphStyle(
        'LabelStyle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.black,
        fontName='Helvetica-Bold'
    )
    
    # Table value style
    value_style = ParagraphStyle(
        'ValueStyle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.black,
        fontName='Helvetica',
        alignment=TA_RIGHT
    )
    
    # Secondary label style (gray text for translations/descriptions)
    secondary_style = ParagraphStyle(
        'SecondaryStyle',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.grey,
        fontName='Helvetica'
    )
    
    # Build information rows
    # Plant/Organization
    info_data.append([
        Paragraph(f"Plant<br/><font color='grey' size='8'>Usine</font>", label_style),
        Paragraph(audit_data.get('plant', 'N/A'), value_style)
    ])
    
    #    if audit_data.get('questionnaire_name') and audit_data.get('questionnaire_name') != audit_data.get('type'):

    # Sector
    questionnaire_name = (audit_data.get('questionnaire_name') or "").lower()

    if audit_data.get('sector'):
        info_data.append([
            Paragraph(f"Sector<br/><font color='grey' size='8'>Secteur</font>", label_style),
            Paragraph(audit_data.get('sector', 'N/A'), value_style)
        ])
    
    #get only date part from audit_date from 2025-12-23 07:00 to 2025-12-23
    audit_date_raw = audit_data.get('audit_date')

    try:
        audit_date_formatted = (
            datetime.fromisoformat(audit_date_raw).date().isoformat()
            if audit_date_raw else 'N/A'
        )
    except ValueError:
        audit_date_formatted = 'N/A'

    info_data.append([
        Paragraph(f"Audit date<br/><font color='grey' size='8'>Date de l'audit</font>", label_style),
        Paragraph(audit_date_formatted, value_style)
    ])
    # Planned Start Date
    #get only hours part from actual_start_date
    actual_start_date_raw = audit_data.get('actual_start_date', 'N/A')
    logger.info(f"Actual Start Date raw: {actual_start_date_raw}")

    # get planned start date if actual_start_date is not available
    if actual_start_date_raw == 'N/A':
        actual_start_date_raw = audit_data.get('planned_start_date', 'N/A')
    
    try:
        dt = datetime.fromisoformat(actual_start_date_raw)
        actual_start_date_formatted = dt.strftime("%H:%M")
    except (TypeError, ValueError):
        actual_start_date_formatted = 'N/A'
    logger.info(f"Actual Start Date formatted: {actual_start_date_formatted}")
    info_data.append([
        Paragraph(f" start date<br/><font color='grey' size='8'>Date de début prévue</font>", label_style),
        Paragraph(actual_start_date_formatted, value_style)
    ])

    actual_end_date_formatted = audit_data.get('actual_end_date', 'N/A')
    # get planned end date if actual_end_date is not available
    if actual_end_date_formatted == 'N/A':
        actual_end_date_formatted = audit_data.get('planned_end_date', 'N/A')
    logger.info(f"Actual End Date raw: {actual_end_date_formatted}")
    try:
        dt = datetime.fromisoformat(actual_end_date_formatted)
        actual_end_date_formatted = dt.strftime("%H:%M")
    except (TypeError, ValueError):
        actual_end_date_formatted = 'N/A'
    logger.info(f"Actual End Date formatted: {actual_end_date_formatted}")
    # Planned End Date
    info_data.append([
        Paragraph(f" end date<br/><font color='grey' size='8'>Date de fin prévue</font>", label_style),
        Paragraph(actual_end_date_formatted, value_style)
    ])
    
    # Audit Type
    info_data.append([
        Paragraph(f"Audit type<br/><font color='grey' size='8'>Type d'audit</font>", label_style),
        Paragraph(audit_data.get('type', 'N/A'), value_style)
    ])
    
    # Questionnaire Name (if different from type)
    if audit_data.get('questionnaire_name') and audit_data.get('questionnaire_name') != audit_data.get('type'):
        info_data.append([
            Paragraph(f"Questionnaire<br/><font color='grey' size='8'>Questionnaire</font>", label_style),
            Paragraph(audit_data.get('questionnaire_name', 'N/A'), value_style)
        ])
    
    # Auditor
    info_data.append([
        Paragraph(f"Auditor<br/><font color='grey' size='8'>Auditeur</font>", label_style),
        Paragraph(audit_data.get('auditor', 'N/A'), value_style)
    ])
    
    # Auditees
    info_data.append([
        Paragraph(f"Auditees<br/><font color='grey' size='8'>Audités</font>", label_style),
        Paragraph(audit_data.get('auditees', 'N/A'), value_style)
    ])
    
    # Create the table
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
    story.append(Spacer(1, 0.5*inch))
    
    # Add footer note if needed
    footer_style = ParagraphStyle(
        'FooterStyle',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.grey,
        alignment=TA_JUSTIFY
    )
    
    # Optional: Add a centered icon/graphic here (like the globe in the reference)
    story.append(Spacer(1, 0.5*inch))
    
    # Add page break after cover
    story.append(PageBreak())


def create_summary_section(story, audit_data, styles):
    """Create the executive summary section"""
    
    # Section title
    section_title = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#1e3a8a'),  # Northwind dark blue
        spaceAfter=12,
        spaceBefore=12,
        fontName='Helvetica-Bold'
    )
    
    story.append(Paragraph("Executive Summary", section_title))
    story.append(Spacer(1, 0.2*inch))
    
    # Check if this is an IATF Plant Manager audit (prefer resolved profile)
    report_profile = (audit_data.get("report_profile") or "").upper()
    questionnaire_name = (audit_data.get('questionnaire_name') or '').lower()
    is_iatf_plant_manager = (
        report_profile == "IATF_PM"
        or ('plant manager' in questionnaire_name and 'iatf' in questionnaire_name)
    )
    
    # Create summary statistics table with conditional terminology
    if is_iatf_plant_manager:
        # IATF PM terminology with score
        summary_data = [
            ['Metric', 'Count'],
            ['Conformities', str(audit_data.get('total_pass', 0))],
            ['Non Conformities', str(audit_data.get('total_fail', 0))],
            ['Needs Improvement', str(audit_data.get('total_improve', 0))],
            ['Not Audited', str(audit_data.get('total_not_audited', 0))],
            ['Total Score', f"{audit_data.get('total_score', 0):.2f}%"],
        ]
    else:
        # Standard terminology with score
        summary_data = [
            ['Metric', 'Count'],
            ['Total Pass', str(audit_data.get('total_pass', 0))],
            ['Total Fail', str(audit_data.get('total_fail', 0))],
            ['Total Needs Improvement', str(audit_data.get('total_improve', 0))],
            ['Total Not Audited', str(audit_data.get('total_not_audited', 0))],
            ['Total Score', f"{audit_data.get('total_score', 0):.2f}%"],
        ]
    
    summary_table = Table(summary_data, colWidths=[3*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        # Header row - Northwind dark blue
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('TOPPADDING', (0, 0), (-1, 0), 12),
        # Data rows - light gray
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f1f5f9')),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e1')),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('TOPPADDING', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
    ]))
    
    story.append(summary_table)
    story.append(Spacer(1, 0.3*inch))
    
    # Strong Points
    story.append(Paragraph("Strong Points", styles['Heading2']))
    story.append(Spacer(1, 0.1*inch))
    strong_points_text = audit_data.get('strong_points', 'No strong points documented.')
    story.append(Paragraph(strong_points_text, styles['Normal']))
    story.append(Spacer(1, 0.2*inch))
    
    # Weak Points / Areas for Improvement
    story.append(Paragraph("Areas for Improvement", styles['Heading2']))
    story.append(Spacer(1, 0.1*inch))
    weak_points_text = audit_data.get('weak_points', 'No weak points documented.')
    story.append(Paragraph(weak_points_text, styles['Normal']))
    story.append(Spacer(1, 0.3*inch))
    
    story.append(PageBreak())


def create_kpi_radar_section(story, audit_data, styles, temp_files_to_cleanup):
    """
    Create the KPI radar chart section for Plant Manager IATF audits
    
    Args:
        story: ReportLab story list to append elements to
        audit_data: Dictionary containing audit information
        styles: ReportLab styles
        temp_files_to_cleanup: List to store temp file paths for cleanup after PDF generation
    """
    # Section title
    section_title = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#1e3a8a'),  # Northwind dark blue
        spaceAfter=12,
        spaceBefore=12,
        fontName='Helvetica-Bold'
    )
    
    story.append(Paragraph("KPI Performance Overview", section_title))
    story.append(Spacer(1, 0.2*inch))
    
    # Add descriptive text
    description_text = (
        "The radar chart below visualizes the audit scores across different KPI categories. "
        "Each axis represents a specific performance area, with scores ranging from 1 to 5. "
        "Areas highlighted in red indicate weak performance (score ≤ 3) requiring immediate attention."
    )
    story.append(Paragraph(description_text, styles['Normal']))
    story.append(Spacer(1, 0.2*inch))
    
    # Generate the radar chart
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
        chart_path = tmp_file.name
    
    try:
        chart_file = create_radar_chart(audit_data, chart_path)
        
        if chart_file and os.path.exists(chart_file):
            # Add the chart to the PDF
            chart_img = Image(chart_file, width=6.5*inch, height=5.4*inch)
            chart_img.hAlign = 'CENTER'
            story.append(chart_img)
            story.append(Spacer(1, 0.2*inch))
            
            # Add interpretation note
            note_style = ParagraphStyle(
                'NoteStyle',
                parent=styles['Normal'],
                fontSize=9,
                textColor=colors.grey,
                alignment=TA_JUSTIFY,
                leftIndent=20,
                rightIndent=20
            )
            
            note_text = (
                "<b>Note:</b> The blue area represents the overall performance across all KPI categories. "
                "Red highlighted sections indicate areas where performance is below the acceptable threshold (≤3) "
                "and require corrective actions or improvement plans."
            )
            story.append(Paragraph(note_text, note_style))
            
            # Store temp file path for cleanup after PDF generation
            temp_files_to_cleanup.append(chart_file)
        else:
            # If chart generation failed, add a message
            story.append(Paragraph(
                "Radar chart could not be generated due to insufficient data.",
                styles['Normal']
            ))
    except Exception as e:
        logger.error(f"Error creating radar chart section: {e}")
        story.append(Paragraph(
            f"Error generating radar chart: {str(e)}",
            styles['Normal']
        ))
    
    story.append(Spacer(1, 0.3*inch))
    story.append(PageBreak())


def create_detailed_findings_section(story, audit_data, styles):
    """Create the detailed findings section with all questions in a table format"""
    
    section_title = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#1e3a8a'),  # Northwind dark blue
        spaceAfter=12,
        spaceBefore=12,
        fontName='Helvetica-Bold'
    )
    
    story.append(Paragraph("Detailed Findings", section_title))
    story.append(Spacer(1, 0.2*inch))
    
    detailed_questions = audit_data.get('detailed_questions', [])
    
    if not detailed_questions:
        story.append(Paragraph("No detailed findings available.", styles['Normal']))
        return
    
    # Define cell text style for table content - smaller font
    cell_style = ParagraphStyle(
        'CellStyle',
        parent=styles['Normal'],
        fontSize=7,
        leading=8,
        alignment=TA_LEFT
    )
    
    # Define header style
    header_style = ParagraphStyle(
        'HeaderStyle',
        parent=styles['Normal'],
        fontSize=7,
        fontName='Helvetica-Bold',
        textColor=colors.whitesmoke,
        alignment=TA_CENTER,
        leading=8
    )
    
    # Create table header with optimized column names
    table_data = [
        [
            Paragraph('Question', header_style),
            Paragraph('Chapter', header_style),
            Paragraph('Findings', header_style),
            Paragraph('Scr', header_style),
            Paragraph('Min', header_style),
            Paragraph('CAR', header_style),
            Paragraph('Due Date', header_style),
        ]
    ]
    
    # Add data rows
    for question in detailed_questions:
        # Question text
        question_text = question.get('question_text', 'N/A')
        
        # Question number
        question_number = str(question.get('chapter', ''))
        
     
        
        # Findings text
        finding_text = question.get('finding_text', '')
        

        
        # value
        value = str(question.get('value', 0))
        
        # Score Min (minimum required score)
        score_min = str(question.get('critical_value', 5))
        
        # Corrective Action details
        car_text = 'No CAR'
        due_date = ''
        if question.get("status")=="fail":
             car_text = 'Critical'
        elif question.get("status")=="improve":
             car_text = 'Improvement'
        elif question.get("status")=="pass":
             car_text = 'No CAR'
       

        corrective_actions = question.get('corrective_action') or []
        car = next((c for c in corrective_actions if c.get('action_type') == 'corrective'), None) \
            or (corrective_actions[0] if corrective_actions else None)
        if car:
            due_date = car.get('due_date', '')

        # Create row with Paragraph objects for text wrapping
        row = [
            Paragraph(question_text, cell_style),
            Paragraph(question_number, cell_style),
                        Paragraph(finding_text, cell_style),

            Paragraph(value, cell_style),
            Paragraph(score_min, cell_style),
            Paragraph(car_text, cell_style),
            Paragraph(due_date, cell_style),
        ]
        
        table_data.append(row)
    
    # Optimized column widths for portrait mode (total ~7 inches)
    col_widths = [
        1.9*inch,   # Question (largest)
        0.60*inch,   # #
        1.5*inch,   # Findings (second largest)
        0.35*inch,  # value
        0.35*inch,  # Score Min
        0.70*inch,  # CAR
        0.6*inch,   # Due Date
    ]
    
    # Create the table
    findings_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    
    # Apply table styling
    findings_table.setStyle(TableStyle([
        # Header row styling - Northwind dark blue
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('TOPPADDING', (0, 0), (-1, 0), 4),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
        
        # Data rows styling
        ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
        ('ALIGN', (1, 1), (2, -1), 'CENTER'),  # Center align numbers
        ('ALIGN', (5, 1), (6, -1), 'CENTER'),  # Center align scores
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('TOPPADDING', (0, 1), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        
        # Grid with slate gray
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('LINEBELOW', (0, 0), (-1, 0), 1.5, colors.HexColor('#1e40af')),
        
        # Alternating row colors - white and light slate
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
    ]))
    
    story.append(findings_table)


def generate_vda_audit_report(audit_data, output_path, logo_path=None):
    """
    Generate a VDA 6.3 Process Audit Report in landscape format
    Following VDA 6.3 Revision 2016 standards
    
    Args:
        audit_data: Dictionary containing all audit information
        output_path: Path where the PDF should be saved
        logo_path: Optional path to company logo
        
    Returns:
        Path to the generated PDF file
    """
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Table, TableStyle
    
    # Ensure output directory exists
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Setup page
    page_width, page_height = landscape(A4)
    c = canvas.Canvas(str(output_path), pagesize=landscape(A4))
    
    # VDA Colors
    dark_green = colors.HexColor('#006B3D')
    black = colors.black
    white = colors.white
    
    # Margins and starting position
    ml, mr, mt, mb = 30, 30, page_height - 30, 30
    curr_y = mt
    
    def format_val(val):
        """Format values for display"""
        if val is None or val == "N/A":
            return ""
        if isinstance(val, datetime):
            return val.strftime("%d/%m/%Y")
        if isinstance(val, float):
            if 0 <= val <= 1:  # Percentage format
                return f"{int(val*100)}%"
            return f"{val:.1f}%"
        return str(val)
    
    # --- HEADER SECTION ---
    c.setFont("Helvetica", 9)
    c.drawString(ml, curr_y, "VDA 6.3 Prozessaudit Revision 2016")
    curr_y -= 12
    c.setLineWidth(1)
    c.line(ml, curr_y, page_width - mr, curr_y)
    curr_y -= 20
    
    # Main Title
    c.setFont("Helvetica-Bold", 12)
    title = "Audit report VDA 6.3 Evaluation of quality capability"
    c.drawCentredString(page_width/2, curr_y, title)
    curr_y -= 25
    
    # --- TOP INFO SECTION ---
    def draw_info_row(x, y, label, value):
        """Draw label-value pair"""
        c.setFont("Helvetica-Bold", 8)
        c.drawString(x, y, label)
        label_w = c.stringWidth(label, "Helvetica-Bold", 8)
        c.setFont("Helvetica", 8)
        c.drawString(x + label_w + 5, y, format_val(value))
    
    # Row 1
    draw_info_row(ml, curr_y, "Supplier:", audit_data.get('plant', 'N/A'))
    draw_info_row(ml + 330, curr_y, "Suppl.-No.:", audit_data.get('supplier_no', ''))
    draw_info_row(ml + 480, curr_y, "J-U-N-S No.:", audit_data.get('duns_no', ''))
    audit_date = audit_data.get('audit_date', 'N/A')
    if audit_date != 'N/A':
        try:
            dt = datetime.fromisoformat(audit_date)
            audit_date = dt.strftime("%d/%m/%Y")
        except:
            pass
    draw_info_row(page_width - mr - 95, curr_y, "Date:", audit_date)
    
    curr_y -= 18
    
    # Row 2
    draw_info_row(ml, curr_y, "Location:", audit_data.get('plant', 'N/A'))
    draw_info_row(ml + 330, curr_y, "Audit request:", audit_data.get('audit_number', ''))
    draw_info_row(ml + 480, curr_y, "Department:", audit_data.get('sector', 'N/A'))
    draw_info_row(page_width - mr - 95, curr_y, "Layer:", "")
    
    curr_y -= 18
    
    # Row 3
    draw_info_row(ml, curr_y, "Audit Reason:", audit_data.get('type', 'N/A'))
    draw_info_row(page_width - mr - 95, curr_y, "Order No.:", audit_data.get('order_no', ''))
    
    curr_y -= 30
    
    # --- LAYOUT SETUP ---
    left_w = 340
    right_w = (page_width - ml - mr) - left_w - 15
    
    # --- RIGHT SIDE: STATEMENTS / REQUIREMENTS TABLE ---
    # Get strengths and weaknesses
    strong_points = audit_data.get('strong_points', 'No strong points documented.')
    weak_points = audit_data.get('weak_points', 'No weak points documented.')
    
    # Format findings
    findings_text = f"<b>Strengths</b><br/>{strong_points}<br/><br/><b>Opportunities for Improvement</b><br/>{weak_points}"
    
        # Get score and rating
    total_score = audit_data.get('total_score', 0)
    rating = audit_data.get("result_class")

    if not rating:
        if total_score >= 90:
            rating = 'A'
        elif total_score >= 80:
            rating = 'B'
        else:
            rating = 'C'
    
    conclusion_text = f"Audit result {total_score:.0f}% rated {rating}."
    
    # Create right table
    normal_style = ParagraphStyle('Normal', fontName='Helvetica', fontSize=7, leading=9)
    bold_style = ParagraphStyle('Bold', fontName='Helvetica-Bold', fontSize=7, leading=9)
    header_style = ParagraphStyle('Header', fontName='Helvetica-Bold', fontSize=8, textColor=white, leading=10)
    
    right_data = [
        [Paragraph("Statements / Requirements", header_style)],
        [Paragraph("Summary of the audit carried out", bold_style)],
        [Paragraph(format_val(audit_data.get('summary', 'Audit completed.')), normal_style)],
        [Paragraph("During the audit the following significant findings were identified:", bold_style)],
        [Paragraph(findings_text, normal_style)],
        [Paragraph("Conclusion", header_style)],
        [Paragraph(conclusion_text, normal_style)],
        [Paragraph("Further action", header_style)],
        [Paragraph("Action plan should be delivered to Mahle 10 working days after receiving this file.", normal_style)],
        [Paragraph("Schedule of action plan", header_style)],
    ]
    
    # Add action plan dates row
    confirm_date = audit_data.get('confirmation_date', '')
    effectiveness_date = audit_data.get('effectiveness_date', '')
    action_dates_row = [
        Paragraph("Confirmation of measures", bold_style),
        Paragraph(format_val(confirm_date), normal_style),
        Paragraph("Effectiveness check", bold_style),
        Paragraph(format_val(effectiveness_date), normal_style)
    ]
    right_data.append(action_dates_row)
    
    # Create right table
    rt = Table(right_data, colWidths=[right_w/4]*4)
    
    # Span cells for all rows except the last one
    for i in range(10):
        rt.setStyle(TableStyle([('SPAN', (0, i), (3, i))]))
    
    rt.setStyle(TableStyle([
        # Header rows background
        ('BACKGROUND', (0, 0), (3, 0), dark_green),
        ('BACKGROUND', (0, 5), (3, 5), dark_green),
        ('BACKGROUND', (0, 7), (3, 7), dark_green),
        ('BACKGROUND', (0, 9), (3, 9), dark_green),
        # Grid
        ('GRID', (0, 0), (-1, -1), 0.5, black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 10), (-1, 10), 'CENTER'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    
    rt_w, rt_h = rt.wrap(right_w, page_height)
    rt.drawOn(c, ml + left_w + 15, curr_y - rt_h)
    
    # --- LEFT SIDE: AUDIT RESULT TABLE ---
    # Get process elements and product groups from detailed questions
    detailed_questions = audit_data.get('detailed_questions', [])
    
    # Build process element summary from computed VDA engine output
    # to avoid inconsistent scaling (e.g. >100%) and "Unknown" labels.
    vda_summary = audit_data.get("vda_result") or {}
    summary_elements = vda_summary.get("elements") or []
    process_elements = []
    for el in summary_elements:
        element_code = str(el.get("element") or "").strip()
        if not element_code:
            continue
        idx = el.get("display_score")
        eg = el.get("eg_percent")
        if eg is None:
            ch_rating = "n.e."
            eg_display = "n.e."
        else:
            eg_num = float(eg)
            eg_display = f"{eg_num:.0f}%"
            if eg_num >= 90:
                ch_rating = "A"
            elif eg_num >= 80:
                ch_rating = "B"
            else:
                ch_rating = "C"
        process_elements.append((
            element_code,
            "n.e." if idx is None else f"{float(idx):.1f}",
            eg_display,
            ch_rating,
        ))
    
    # Fill remaining rows
    while len(process_elements) < 4:
        process_elements.append(('n.e.', 'n.e.', 'n.e.', 'n.e.'))
    
    # Create audit result table
    audit_result_style = ParagraphStyle(
        'AuditResult',
        fontName='Helvetica-Bold',
        fontSize=7,
        leading=8,
        alignment=TA_LEFT,
        wordWrap='CJK',
    )

    t1_data = [
        ['Audit result', '', '', ''],
        ['Evaluated process element', 'Evaluation Index', 'EG [%]', 'Rating'],
        [Paragraph(str(audit_data.get('questionnaire_name', 'VDA 6.3')), audit_result_style), '', f"{total_score:.0f}%", rating],
        ['Evaluated product group', '', '', ''],
    ]
    
    # Add process elements
    for elem in process_elements:
        t1_data.append(list(elem))
    
    t1 = Table(t1_data, colWidths=[left_w*0.4, left_w*0.25, left_w*0.2, left_w*0.15])
    t1.setStyle(TableStyle([
        ('SPAN', (0, 0), (3, 0)),
        ('SPAN', (0, 3), (3, 3)),
        ('BACKGROUND', (0, 0), (3, 0), dark_green),
        ('TEXTCOLOR', (0, 0), (3, 0), white),
        ('GRID', (0, 0), (-1, -1), 0.5, black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 2), (0, 2), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (3, 1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    
    t1_w, t1_h = t1.wrap(left_w, page_height)
    t1.drawOn(c, ml, curr_y - t1_h)
    
    # Classification scale
    curr_y -= (t1_h + 10)
    c.setFont("Helvetica", 6)
    scale_text = "Classification scale: A = 90 - 100% quality capable; B = 80 - < 90% conditionally quality capable; C = 0 - < 80% not quality capable"
    c.drawString(ml, curr_y, scale_text)
    
    # --- LAST AUDIT RESULTS TABLE ---
    curr_y -= 40
    t2_data = [
        ['Last Audit Results / Certificates', '', '', ''],
        ['Certificate / Audit No:', 'Issue Date', 'Conducted by', 'Result'],
        ['', '', '', ''],
        ['', '', '', ''],
        ['', '', '', ''],
        ['', '', '', '']
    ]
    
    t2 = Table(t2_data, colWidths=[left_w*0.3, left_w*0.2, left_w*0.25, left_w*0.25], rowHeights=14)
    t2.setStyle(TableStyle([
        ('SPAN', (0, 0), (3, 0)),
        ('BACKGROUND', (0, 0), (3, 0), dark_green),
        ('TEXTCOLOR', (0, 0), (3, 0), white),
        ('GRID', (0, 0), (-1, -1), 0.5, black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTSIZE', (0, 0), (-1, -1), 6.5),
    ]))
    
    t2_w, t2_h = t2.wrap(left_w, page_height)
    t2.drawOn(c, ml, curr_y - t2_h)
    
    # --- AUDIT TEAM TABLE ---
    curr_y -= (t2_h + 25)
    
    auditor_name = audit_data.get('auditor', 'N/A')
    auditees = audit_data.get('auditees', 'N/A')
    
    t3_data = [
        ['Audit team:', 'Audit Organization:', '(Supplier)'],
        [f"{auditor_name}", audit_data.get('plant', ''), f"Senior: {auditees}"],
        ['', '', f"Plant Management: {audit_data.get('plant', '')}"],
        ['', '', 'Q-Management: ']
    ]
    
    t3 = Table(t3_data, colWidths=[left_w*0.3, left_w*0.3, left_w*0.4], rowHeights=14)
    t3.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (2, 0), dark_green),
        ('TEXTCOLOR', (0, 0), (2, 0), white),
        ('GRID', (0, 0), (-1, -1), 0.5, black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTSIZE', (0, 0), (-1, -1), 6.5),
    ]))
    
    t3_w, t3_h = t3.wrap(left_w, page_height)
    t3.drawOn(c, ml, curr_y - t3_h)
    
    # --- FOOTER SIGNATURE SECTION ---
    foot_y = 45
    
    # Auditor
    c.setFont("Helvetica", 8)
    c.drawString(ml, foot_y, "Auditor:")
    c.drawCentredString(ml+92, foot_y+5, auditor_name)
    c.line(ml+35, foot_y-2, ml+150, foot_y-2)
    c.setFont("Helvetica", 6.5)
    c.drawCentredString(ml+92, foot_y-12, audit_data.get('auditor_certificate', ''))
    
    # Co-Auditor
    c.setFont("Helvetica", 8)
    co_auditor = audit_data.get('co_auditor', '')
    c.drawString(ml+200, foot_y, "Co Auditor:")
    c.drawCentredString(ml+292, foot_y+5, format_val(co_auditor))
    c.line(ml+245, foot_y-2, ml+360, foot_y-2)
    c.setFont("Helvetica", 6.5)
    c.drawCentredString(ml+292, foot_y-12, format_val(audit_data.get('co_auditor_certificate', '')))
    
    # Signed by organization
    c.setFont("Helvetica", 8)
    c.drawString(page_width-mr-160, foot_y, "Signed by (organisation):")
    c.line(page_width-mr-110, foot_y-2, page_width - mr, foot_y-2)
    
    # --- PAGE 2: Detailed VDA scores (computed at report-time) ---
    vda_result = audit_data.get("vda_result") or {}
    elements = vda_result.get("elements") or []
    if elements:
        c.showPage()
        page_width, page_height = landscape(A4)
        total = vda_result.get("total", {})
        p6_subgroups = vda_result.get("ep6_subgroups") or {}
        p3_p4_process_types = vda_result.get("p3_p4_process_types") or {}
        downgrade_reasons = vda_result.get("downgrade_reasons") or []

        def fmt_pct(value):
            return "n.e." if value is None else f"{float(value):.1f}%"

        def fmt_display(value):
            return "n.e." if value is None else str(value)

        def draw_header_band(y_top):
            c.setFillColor(colors.HexColor("#F3F8F5"))
            c.rect(24, y_top - 34, page_width - 48, 28, fill=1, stroke=0)
            c.setFillColor(dark_green)
            c.setFont("Helvetica-Bold", 16)
            c.drawString(30, y_top - 20, "VDA 6.3 Detailed Evaluation Matrix")
            c.setFillColor(colors.black)
            c.setFont("Helvetica", 8.5)
            c.drawString(30, y_top - 42, f"Audit: {audit_data.get('audit_number', 'N/A')}")
            c.drawString(210, y_top - 42, f"Plant: {audit_data.get('plant', 'N/A')}")
            c.drawString(390, y_top - 42, f"Questionnaire: {audit_data.get('questionnaire_name', 'VDA 6.3')}")
            c.drawRightString(page_width - 30, y_top - 42, f"Class: {audit_data.get('result_class', 'N/A')}")

        def draw_total_summary(x, y_top, width, height):
            c.setFillColor(colors.HexColor("#F8FAFC"))
            c.roundRect(x, y_top - height, width, height, 8, fill=1, stroke=0)
            c.setStrokeColor(colors.HexColor("#C7D2E0"))
            c.roundRect(x, y_top - height, width, height, 8, fill=0, stroke=1)
            c.setFillColor(dark_green)
            c.setFont("Helvetica-Bold", 10)
            c.drawString(x + 12, y_top - 18, "Overall Compliance")
            c.setFillColor(colors.black)
            c.setFont("Helvetica", 8)
            c.drawString(x + 12, y_top - 34, "Achieved / Max")
            c.drawString(x + 12, y_top - 48, "EG [%]")
            c.drawString(x + 12, y_top - 62, "Display / Rating")
            c.setFont("Helvetica-Bold", 11)
            c.drawRightString(x + width - 12, y_top - 34, f"{total.get('achieved_points', 0)} / {total.get('max_points', 0)}")
            c.drawRightString(x + width - 12, y_top - 48, fmt_pct(total.get("eg_percent")))
            c.drawRightString(
                x + width - 12,
                y_top - 62,
                f"{fmt_display(total.get('display_score'))} / {total.get('final_rating', 'n.e.')}",
            )

        def build_elements_table():
            table_data = [[
                "Element", "Answered", "Total", "Achieved", "Max", "EG %", "Display",
            ]]
            for el in elements:
                table_data.append([
                    str(el.get("element", "")),
                    str(el.get("answered", 0)),
                    str(el.get("total", 0)),
                    str(el.get("achieved_points", 0)),
                    str(el.get("max_points", 0)),
                    fmt_pct(el.get("eg_percent")),
                    fmt_display(el.get("display_score")),
                ])
            table_data.append([
                "TOTAL", "", "",
                str(total.get("achieved_points", 0)),
                str(total.get("max_points", 0)),
                fmt_pct(total.get("eg_percent")),
                fmt_display(total.get("display_score")),
            ])
            return table_data

        def draw_matrix_table(x, y_top, width):
            table_data = build_elements_table()
            dt = Table(
                table_data,
                colWidths=[84, 68, 58, 72, 72, 64, 64],
                rowHeights=20,
            )
            dt.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), dark_green),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#7C8A96")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F8FAFC")]),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EAF4EE")),
            ]))
            tw, th = dt.wrap(width, page_height)
            dt.drawOn(c, x, y_top - th)
            return th

        def draw_detail_box(x, y_top, width, title, subtitle, rows):
            height = 26 + (len(rows) * 16) + 12
            c.setFillColor(colors.white)
            c.roundRect(x, y_top - height, width, height, 7, fill=1, stroke=0)
            c.setStrokeColor(colors.HexColor("#C7D2E0"))
            c.roundRect(x, y_top - height, width, height, 7, fill=0, stroke=1)
            c.setFillColor(dark_green)
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
                ("EG / Display", f"{fmt_pct(el.get('eg_percent'))} / {fmt_display(el.get('display_score'))}"),
            ]

        def detail_rows_for_process_map(proc_map):
            ordered_keys = ["product", "process_support", "unspecified"]
            rows = []
            for key in ordered_keys:
                info = proc_map.get(key)
                if not info:
                    continue
                label = {
                    "product": "Product",
                    "process_support": "Process",
                    "unspecified": "Unspecified",
                }[key]
                rows.append((label, f"{info.get('achieved_points', 0)} pts / {info.get('answered', 0)} ans."))
            return rows or [("Breakdown", "n.e.")]

        def detail_rows_for_subgroups(subgroups):
            ordered = ["6.1", "6.2", "6.3", "6.4", "6.5", "6.6"]
            rows = []
            for key in ordered:
                info = subgroups.get(key)
                if not info:
                    continue
                rows.append((key, f"{fmt_pct(info.get('eg_percent'))} / {info.get('answered', 0)} of {info.get('total', 0)}"))
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
                c.drawString(x + 10, y_top - 34, "No downgrade rule triggered during this audit.")
            if has_reasons:
                c.drawString(x + 10, y_top - height + 16, "At least 2/3 of the questions must be answered for each evaluated element.")
            return height

        draw_header_band(page_height - 18)
        draw_total_summary(page_width - 240, page_height - 64, 210, 76)

        table_height = draw_matrix_table(30, page_height - 88, page_width - 300)

        detail_top = page_height - 108 - table_height
        left_x = 30
        mid_x = 270
        right_x = 510
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
        c.setFillColor(dark_green)
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
        c.drawRightString(
            summary_x + 248,
            summary_y - 66,
            f"{fmt_pct(total.get('eg_percent'))} / {total.get('final_rating', 'n.e.')}",
        )
        c.setFont("Helvetica", 7.5)
        c.drawString(summary_x + 10, summary_y - 82, "Detailed visual layout inspired by the VDA matrix worksheet.")

    # --- PAGE 3: Action plan with defined immediate action (dynamic, available fields only) ---
    c.showPage()
    page_width, page_height = landscape(A4)

    supplier_text = str(audit_data.get("auditees", "N/A"))
    if isinstance(audit_data.get("auditees"), list):
      supplier_text = ", ".join(str(x) for x in audit_data.get("auditees", []) if x) or "N/A"

    def draw_action_plan_header():
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(30, page_height - 30, "Action plan with defined immediate action")

        c.setFont("Helvetica-Bold", 9)
        c.drawString(30, page_height - 52, "Supplier:")
        c.drawString(30, page_height - 68, "Location:")
        c.drawString(page_width - 220, page_height - 52, "Order No.:")
        c.drawString(page_width - 220, page_height - 68, "Date:")

        c.setFont("Helvetica", 9)
        c.drawString(95, page_height - 52, supplier_text)
        c.drawString(95, page_height - 68, str(audit_data.get("plant", "N/A")))
        c.drawString(page_width - 160, page_height - 52, str(audit_data.get("audit_number", "N/A")))
        c.drawString(page_width - 160, page_height - 68, str(audit_data.get("audit_date", "N/A")))

    def draw_action_plan_footer():
        c.setFont("Helvetica", 8.5)
        c.setFillColor(colors.black)
        c.drawString(30, 22, "Audit VDA6.3 (1)")
        c.drawRightString(page_width - 30, 22, "Copyright VDA QMC 2016")

    # Plain strings never wrap in a reportlab Table cell; long findings
    # need a Paragraph (markup-escaped, newlines kept as line breaks).
    action_cell_style = ParagraphStyle(
        "ActionPlanCell",
        fontName="Helvetica",
        fontSize=7,
        leading=8.5,
        alignment=TA_LEFT,
        wordWrap="CJK",
    )
    action_cell_center_style = ParagraphStyle(
        "ActionPlanCellCenter", parent=action_cell_style, alignment=TA_CENTER
    )

    def action_cell(value, style=action_cell_style):
        text = str(value or "")
        if not text:
            return ""
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return Paragraph(text.replace("\r\n", "\n").replace("\n", "<br/>"), style)

    # Build rows from available data.
    # Prefer detailed_questions (always present in report payload).
    records = (
        audit_data.get("detailed_questions")
        or audit_data.get("answers")
        or []
    )

    grouped = {}
    for rec in records:
        q_code = str(
            rec.get("question_code")
            or rec.get("chapter")
            or rec.get("standard_paragraph")
            or ""
        )
        element = str(rec.get("element") or (q_code.split(".")[0] if q_code else "P?"))
        grouped.setdefault(element, []).append(rec)

    def normalize_reference_label(value: str) -> str:
        v = (value or "").strip().lower()
        if "product" in v:
            return "Product"
        if "process" in v:
            return "Process"
        return ""

    # table header and data
    table_data = [[
        "Filled in by the auditor in the questionnaire",
        "", "", "", "",
        "Filled in by the audited area",
        "", "", "", "",
    ], [
        "Question No.",
        "Reference",
        "Audit results",
        "Points",
        "Immediate\naction",
        "Reason(s)",
        "Measure(s)",
        "Deadline",
        "Responsibility",
        "Effectivity",
    ]]

    section_row_indexes = []
    for element in sorted(grouped.keys()):
        section_label = f"{element} {str(audit_data.get('section_titles', {}).get(element, '')).strip()}".strip()
        section_row_indexes.append(len(table_data))
        table_data.append([section_label, "", "", "", "", "", "", "", "", ""])
        for ans in grouped[element]:
            corrective_actions = ans.get("corrective_action") or []
            car = next((c for c in corrective_actions if c.get('action_type') == 'corrective'), None) \
                or (corrective_actions[0] if corrective_actions else None) or {}
            has_immediate_action = any(c.get('action_type') == 'immediate' for c in corrective_actions)
            q_no = str(
                ans.get("question_code")
                or ans.get("standard_paragraph")
                or ans.get("identifier")
                or "N/A"
            )
            raw_reference = str(
                ans.get("process")
                or ans.get("chapter")
                or ans.get("standard_paragraph")
                or ""
            )
            reference = normalize_reference_label(raw_reference)
            findings = str(ans.get("finding_text") or "")
            points = str(ans.get("value") if ans.get("value") is not None else "n.e.")
            immediate_required = bool(
                ans.get("immediate_action_required")
                or has_immediate_action
            )
            immediate = "Yes" if immediate_required else "n.e."
            reason = str(
                car.get("reason_why")
                or ans.get("car_reason")
                or findings
                or ""
            )
            measure = str(
                car.get("implemented_solution")
                or ans.get("implemented_solution")
                or ""
            )
            deadline = str(
                car.get("submission_due_at")
                or car.get("due_date")
                or ans.get("submission_due_at")
                or ans.get("due_date")
                or ""
            )
            # Right-side columns are intentionally left empty for auditee completion.
            responsibility = ""
            effectivity = ""
            reason = ""
            measure = ""
            deadline = ""
            table_data.append([
                action_cell(q_no),
                action_cell(reference),
                action_cell(findings),
                action_cell(points, action_cell_center_style),
                action_cell(immediate, action_cell_center_style),
                action_cell(reason),
                action_cell(measure),
                action_cell(deadline),
                responsibility,
                effectivity,
            ])

    if len(table_data) == 2:
        table_data.append([
            action_cell("N/A"),
            "",
            action_cell("No answered questions were captured for this audit."),
            "",
            "",
            "",
            "",
            "",
            "",
            "",
        ])

    action_table = Table(
        table_data,
        # Sums to the 782pt printable width (landscape A4 minus 30pt margins).
        colWidths=[58, 52, 196, 32, 62, 98, 98, 54, 70, 62],
        repeatRows=2,
        splitByRow=1,
        # A single finding can be taller than a page. Continue that row on
        # the following page instead of drawing it through the footer.
        splitInRow=1,
    )
    action_table.setStyle(TableStyle([
        ("SPAN", (0, 0), (4, 0)),
        ("SPAN", (5, 0), (9, 0)),
        ("BACKGROUND", (0, 0), (4, 0), colors.HexColor("#D9D9D9")),
        ("BACKGROUND", (5, 0), (9, 0), colors.HexColor("#D9D9D9")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8.5),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("BACKGROUND", (0, 1), (-1, 1), dark_green),
        ("TEXTCOLOR", (0, 1), (-1, 1), colors.white),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, 1), 7),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.black),
        ("ALIGN", (3, 2), (4, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, 1), "MIDDLE"),
        ("VALIGN", (0, 2), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 2), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 2), (-1, -1), 4),
        ("FONTSIZE", (0, 2), (-1, -1), 7),
    ]))

    # style section rows
    for i in section_row_indexes:
        action_table.setStyle(TableStyle([
            ("SPAN", (0, i), (-1, i)),
            ("BACKGROUND", (0, i), (-1, i), colors.HexColor("#595959")),
            ("TEXTCOLOR", (0, i), (-1, i), colors.white),
            ("FONTNAME", (0, i), (-1, i), "Helvetica-Bold"),
            ("VALIGN", (0, i), (-1, i), "MIDDLE"),
        ]))

    # Split the table across as many pages as it needs (the two header rows
    # repeat on each page) instead of drawing it once, which let a long
    # table run up over the page header.
    table_top = page_height - 80
    table_bottom = 40
    avail_width = page_width - 60
    avail_height = table_top - table_bottom
    pending_parts = [action_table]
    draw_action_plan_header()
    while pending_parts:
        part = pending_parts.pop(0)
        _, part_height = part.wrap(avail_width, avail_height)
        if part_height > avail_height:
            pieces = part.split(avail_width, avail_height)
            if not pieces:
                raise ValueError(
                    "The VDA action-plan table contains content that cannot fit on a page."
                )
            part = pieces[0]
            pending_parts = list(pieces[1:]) + pending_parts
            _, part_height = part.wrap(avail_width, avail_height)
        part.drawOn(c, 30, table_top - part_height)
        draw_action_plan_footer()
        if pending_parts:
            c.showPage()
            draw_action_plan_header()

    if str(audit_data.get("report_profile", "")).upper() == "VDA_COMBINED" and audit_data.get("p1_result"):
        draw_vda_p1_appendix_page(c, audit_data, logo_path)

    c.save()
    
    print(f"VDA Report generated successfully: {output_path}")
    return output_path


def generate_vda_p1_report(audit_data, output_path, logo_path=None):
    """
    Generate a dedicated VDA P1 Potential Analysis report.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Table, TableStyle

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    c = canvas.Canvas(str(output_path), pagesize=A4)
    page_width, page_height = A4

    p1 = (audit_data.get("vda_result") or {}).get("p1_result") or {}
    red = int(p1.get("red", 0))
    yellow = int(p1.get("yellow", 0))
    green = int(p1.get("green", 0))
    ne = int(p1.get("ne", 0))
    cls = str(p1.get("classification", "N/A"))
    label = str(p1.get("label", "N/A"))
    margin = 28
    content_w = page_width - (2 * margin)

    # Palette
    brand_dark = colors.HexColor("#0E3A5B")
    brand_light = colors.HexColor("#EAF2F8")
    neutral_border = colors.HexColor("#C9D3DD")
    text_dark = colors.HexColor("#1F2933")
    red_c = colors.HexColor("#D7263D")
    yellow_c = colors.HexColor("#F4B400")
    green_c = colors.HexColor("#1B9E4B")
    gray_c = colors.HexColor("#6B7280")

    # Header band
    header_h = 72
    c.setFillColor(brand_dark)
    c.roundRect(margin, page_height - margin - header_h, content_w, header_h, 8, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(margin + 16, page_height - margin - 26, "VDA P1 Potential Analysis")
    c.setFont("Helvetica", 10)
    c.drawString(margin + 16, page_height - margin - 44, "Dedicated audit summary report")

    # Optional logo
    chosen_logo = None
    for candidate in [logo_path, "app/assets/logo-northwind.jpg"]:
        if candidate and os.path.exists(candidate):
            chosen_logo = candidate
            break
    if chosen_logo:
        try:
            c.drawImage(
                chosen_logo,
                page_width - margin - 92,
                page_height - margin - 58,
                width=76,
                height=42,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass

    y = page_height - margin - header_h - 16

    # Metadata panel
    meta_h = 64
    c.setFillColor(brand_light)
    c.setStrokeColor(neutral_border)
    c.roundRect(margin, y - meta_h, content_w, meta_h, 6, stroke=1, fill=1)
    c.setFillColor(text_dark)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin + 14, y - 20, "Audit No.")
    c.drawString(margin + 190, y - 20, "Date")
    c.drawString(margin + 320, y - 20, "Plant")
    c.drawString(margin + 430, y - 20, "Questionnaire")
    c.setFont("Helvetica", 10)
    c.drawString(margin + 14, y - 38, str(audit_data.get("audit_number", "N/A")))
    c.drawString(margin + 190, y - 38, str(audit_data.get("audit_date", "N/A")))
    c.drawString(margin + 320, y - 38, str(audit_data.get("plant", "N/A")))
    q_name = str(audit_data.get("questionnaire_name", "N/A"))
    c.drawString(margin + 430, y - 38, q_name[:20] + ("..." if len(q_name) > 20 else ""))

    y = y - meta_h - 16

    # KPI cards
    card_h = 88
    gap = 8
    card_w = (content_w - (3 * gap)) / 4
    kpis = [
        ("Red", red, red_c),
        ("Yellow", yellow, yellow_c),
        ("Green", green, green_c),
        ("n.e.", ne, gray_c),
    ]
    x = margin
    for title, value, tone in kpis:
        c.setFillColor(colors.white)
        c.setStrokeColor(neutral_border)
        c.roundRect(x, y - card_h, card_w, card_h, 6, stroke=1, fill=1)
        c.setFillColor(tone)
        c.rect(x, y - 6, card_w, 6, stroke=0, fill=1)
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(x + 10, y - 24, title)
        c.setFont("Helvetica-Bold", 24)
        c.drawRightString(x + card_w - 10, y - 52, str(value))
        c.setFont("Helvetica", 8.5)
        c.setFillColor(gray_c)
        c.drawString(x + 10, y - 68, "Questions counted")
        x += card_w + gap

    y = y - card_h - 18

    # Classification banner
    cls_map = {"R": red_c, "Y": yellow_c, "G": green_c}
    cls_color = cls_map.get(cls, brand_dark)
    banner_h = 52
    c.setFillColor(cls_color)
    c.roundRect(margin, y - banner_h, content_w, banner_h, 8, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin + 14, y - 20, "Final Classification")
    c.setFont("Helvetica-Bold", 18)
    c.drawRightString(margin + content_w - 14, y - 22, f"{cls} - {label}")

    y = y - banner_h - 16

    # Rules table
    table_data = [
        ["Class", "Condition (Yellow)", "Condition (Red)"],
        ["R - Barred supplier", "more than 12", "one or more"],
        ["Y - Conditionally approved supplier", "max. 12", "none"],
        ["G - Approved supplier", "max. 6", "none"],
    ]
    rules_table = Table(table_data, colWidths=[180, 170, 170], repeatRows=1)
    rules_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), brand_dark),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, neutral_border),
        ("BACKGROUND", (0, 1), (-1, -1), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    tw, th = rules_table.wrap(content_w, 200)
    rules_table.drawOn(c, margin, y - th)
    y = y - th - 14

    # Interpretation notes
    c.setFillColor(text_dark)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin, y, "Interpretation")
    y -= 14
    c.setFont("Helvetica", 9.5)
    notes = [
        "Green: approved supplier.",
        "Yellow: conditionally approved supplier.",
        "Red: barred supplier.",
        "Rule summary: Red >= 1 OR Yellow > 12 => class R.",
        "If Red = 0 and Yellow <= 6 => class G; otherwise class Y.",
    ]
    for note in notes:
        c.drawString(margin + 10, y, f"- {note}")
        y -= 12

    # Footer
    c.setStrokeColor(neutral_border)
    c.line(margin, 30, page_width - margin, 30)
    c.setFillColor(gray_c)
    c.setFont("Helvetica", 8)
    c.drawString(margin, 18, "Audit VDA P1 Potential Analysis")
    c.drawRightString(page_width - margin, 18, "Copyright VDA QMC 2016")

    c.save()
    print(f"VDA P1 report generated successfully: {output_path}")
    return output_path


def draw_vda_p1_appendix_page(c, audit_data, logo_path=None):
    """
    Draw a compact VDA P1 appendix page onto an existing canvas.
    Used when a single audit contains both P1 and VDA 6.3 sections.
    """
    from reportlab.lib.pagesizes import A4

    page_width, page_height = A4

    p1 = audit_data.get("p1_result") or (audit_data.get("vda_result") or {}).get("p1_result") or {}
    red = int(p1.get("red", 0))
    yellow = int(p1.get("yellow", 0))
    green = int(p1.get("green", 0))
    ne = int(p1.get("ne", 0))
    cls = str(p1.get("classification", "N/A"))
    label = str(p1.get("label", "N/A"))

    margin = 28
    content_w = page_width - (2 * margin)

    brand_dark = colors.HexColor("#0E3A5B")
    brand_light = colors.HexColor("#EAF2F8")
    neutral_border = colors.HexColor("#C9D3DD")
    text_dark = colors.HexColor("#1F2933")
    red_c = colors.HexColor("#D7263D")
    yellow_c = colors.HexColor("#F4B400")
    green_c = colors.HexColor("#1B9E4B")
    gray_c = colors.HexColor("#6B7280")

    c.showPage()
    c.setPageSize(A4)
    c.setTitle("VDA P1 Appendix")

    header_h = 72
    c.setFillColor(brand_dark)
    c.roundRect(margin, page_height - margin - header_h, content_w, header_h, 8, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(margin + 16, page_height - margin - 26, "VDA P1 Potential Analysis")
    c.setFont("Helvetica", 10)
    c.drawString(margin + 16, page_height - margin - 44, "Appendix to the combined VDA 6.3 report")

    chosen_logo = None
    for candidate in [logo_path, "app/assets/logo-northwind.jpg"]:
        if candidate and os.path.exists(candidate):
            chosen_logo = candidate
            break
    if chosen_logo:
        try:
            c.drawImage(
                chosen_logo,
                page_width - margin - 92,
                page_height - margin - 58,
                width=76,
                height=42,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass

    y = page_height - margin - header_h - 16

    meta_h = 64
    c.setFillColor(brand_light)
    c.setStrokeColor(neutral_border)
    c.roundRect(margin, y - meta_h, content_w, meta_h, 6, stroke=1, fill=1)
    c.setFillColor(text_dark)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin + 14, y - 20, "Audit No.")
    c.drawString(margin + 190, y - 20, "Date")
    c.drawString(margin + 320, y - 20, "Plant")
    c.drawString(margin + 430, y - 20, "Questionnaire")
    c.setFont("Helvetica", 10)
    c.drawString(margin + 14, y - 38, str(audit_data.get("audit_number", "N/A")))
    c.drawString(margin + 190, y - 38, str(audit_data.get("audit_date", "N/A")))
    c.drawString(margin + 320, y - 38, str(audit_data.get("plant", "N/A")))
    q_name = str(audit_data.get("questionnaire_name", "N/A"))
    c.drawString(margin + 430, y - 38, q_name[:20] + ("..." if len(q_name) > 20 else ""))

    y = y - meta_h - 16

    card_h = 88
    gap = 8
    card_w = (content_w - (3 * gap)) / 4
    kpis = [
        ("Red", red, red_c),
        ("Yellow", yellow, yellow_c),
        ("Green", green, green_c),
        ("n.e.", ne, gray_c),
    ]
    x = margin
    for title, value, tone in kpis:
        c.setFillColor(colors.white)
        c.setStrokeColor(neutral_border)
        c.roundRect(x, y - card_h, card_w, card_h, 6, stroke=1, fill=1)
        c.setFillColor(tone)
        c.rect(x, y - 6, card_w, 6, stroke=0, fill=1)
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(x + 10, y - 24, title)
        c.setFont("Helvetica-Bold", 24)
        c.drawRightString(x + card_w - 10, y - 52, str(value))
        c.setFont("Helvetica", 8.5)
        c.setFillColor(gray_c)
        c.drawString(x + 10, y - 68, "Questions counted")
        x += card_w + gap

    y = y - card_h - 18

    cls_map = {"R": red_c, "Y": yellow_c, "G": green_c}
    cls_color = cls_map.get(cls, brand_dark)
    banner_h = 52
    c.setFillColor(cls_color)
    c.roundRect(margin, y - banner_h, content_w, banner_h, 8, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin + 14, y - 20, "Final Classification")
    c.setFont("Helvetica-Bold", 18)
    c.drawRightString(margin + content_w - 14, y - 22, f"{cls} - {label}")

    y = y - banner_h - 16

    table_data = [
        ["Class", "Condition (Yellow)", "Condition (Red)"],
        ["R - Barred supplier", "more than 12", "one or more"],
        ["Y - Conditionally approved supplier", "max. 12", "none"],
        ["G - Approved supplier", "max. 6", "none"],
    ]
    rules_table = Table(table_data, colWidths=[180, 170, 170], repeatRows=1)
    rules_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), brand_dark),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, neutral_border),
        ("BACKGROUND", (0, 1), (-1, -1), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    tw, th = rules_table.wrap(content_w, 200)
    rules_table.drawOn(c, margin, y - th)
    y = y - th - 14

    c.setFillColor(text_dark)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin, y, "Interpretation")
    y -= 14
    c.setFont("Helvetica", 9.5)
    notes = [
        "Green: approved supplier.",
        "Yellow: conditionally approved supplier.",
        "Red: barred supplier.",
        "Rule summary: Red >= 1 OR Yellow > 12 => class R.",
        "If Red = 0 and Yellow <= 6 => class G; otherwise class Y.",
    ]
    for note in notes:
        c.drawString(margin + 10, y, f"- {note}")
        y -= 12

    c.setStrokeColor(neutral_border)
    c.line(margin, 30, page_width - margin, 30)
    c.setFillColor(gray_c)
    c.setFont("Helvetica", 8)
    c.drawString(margin, 18, "Audit VDA P1 Potential Analysis")
    c.drawRightString(page_width - margin, 18, "Copyright VDA QMC 2016")


def generate_audit_report(audit_data, output_path, logo_path=None):
    """
    Generate a complete audit report PDF
    Routes to appropriate report format based on questionnaire type
    
    Args:
        audit_data: Dictionary containing all audit information
        output_path: Path where the PDF should be saved
        logo_path: Optional path to company logo
        
    Returns:
        Path to the generated PDF file
    """
    # Resolve report profile (prefer upstream resolver payload)
    report_profile = (audit_data.get("report_profile") or "").upper()
    questionnaire_name = (audit_data.get('questionnaire_name') or '').lower()

    if report_profile == "VDA_P1":
        return generate_vda_p1_report(audit_data, output_path, logo_path)
    if report_profile in {"VDA", "VDA_COMBINED"} or ('vda' in questionnaire_name):
        # Generate VDA 6.3 format report
        return generate_vda_audit_report(audit_data, output_path, logo_path)
    if report_profile == "IATF_NC" or ('iatf' in questionnaire_name and 'plant manager' not in questionnaire_name):
        return generate_iatf_nc_report(audit_data, output_path, logo_path)
    # Otherwise, generate standard report
    # Ensure output directory exists
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # List to store temporary files for cleanup
    temp_files_to_cleanup = []
    
    # Create the PDF document
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=0.75*inch,
        leftMargin=0.75*inch,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch,
        author=audit_data.get('auditor', 'Audit System'),
        title=f"Audit Report - {audit_data.get('audit_number', 'N/A')}",
        subject=f"Audit Report for {audit_data.get('plant', 'N/A')}",
    )
    
    # Container for the 'Flowable' objects
    story = []
    
    # Get styles
    styles = getSampleStyleSheet()
    
    # Add custom styles
    styles.add(ParagraphStyle(
        name='Justify',
        parent=styles['Normal'],
        alignment=TA_JUSTIFY,
    ))
    
    # Create cover page
    create_cover_page(story, audit_data, logo_path, styles)
    
    # Create summary section
    create_summary_section(story, audit_data, styles)
    
    # Check if this is a Plant Manager IATF audit and add radar chart
    if report_profile == "IATF_PM" or ('plant manager' in questionnaire_name and 'iatf' in questionnaire_name):
        create_kpi_radar_section(story, audit_data, styles, temp_files_to_cleanup)
    
    # Create detailed findings section
    create_detailed_findings_section(story, audit_data, styles)
    
    # Build the PDF
    doc.build(story)
    
    # Clean up temporary files after PDF is built
    for temp_file in temp_files_to_cleanup:
        try:
            if os.path.exists(temp_file):
                os.unlink(temp_file)
                logger.info(f"Cleaned up temporary file: {temp_file}")
        except Exception as e:
            logger.warning(f"Could not delete temporary file {temp_file}: {e}")
    
    print(f"Report generated successfully: {output_path}")
    return output_path



def create_email_body(audit_data: dict, custom_message: Optional[str] = None) -> str:
    """
    Create a professional HTML email body for the audit report
    
    Args:
        audit_data: Dictionary with audit information
        custom_message: Optional custom message to include
        
    Returns:
        HTML string for email body
    """
    # Check if this is an IATF Plant Manager audit (prefer resolved profile)
    report_profile = (audit_data.get("report_profile") or "").upper()
    questionnaire_name = (audit_data.get('questionnaire_name') or '').lower()
    is_iatf_plant_manager = (
        report_profile == "IATF_PM"
        or ('plant manager' in questionnaire_name and 'iatf' in questionnaire_name)
    )
    
    custom_msg_html = ""
    if custom_message:
        custom_msg_html = f"""
        <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 20px 0;">
            <p style="margin: 0; color: #495057; line-height: 1.6;">
                {custom_message}
            </p>
        </div>
        """
    
    # Score row
    score_row = f"""
    <tr>
        <td style="color: #6c757d; font-size: 14px; padding: 5px 0;">
            <strong>Final Score:</strong>
        </td>
        <td style="color: #495057; font-size: 14px; padding: 5px 0; text-align: right;">
            <strong style="color: #28a745; font-size: 18px;">
                {audit_data.get('total_score', 0):.1f}%
            </strong>
        </td>
    </tr>
    """
    sector_row=""
    if audit_data.get('sector'):
        sector_row=f"""
                                              <tr>
                                                    <td style="color: #6c757d; font-size: 14px; padding: 5px 0;">
                                                        <strong>Sector:</strong>
                                                    </td>
                                                    <td style="color: #495057; font-size: 14px; padding: 5px 0; text-align: right;">
                                                        {audit_data.get('sector', 'N/A')}
                                                    </td>
                                                </tr>
        """

    combined_report_note = ""
    if report_profile == "VDA_COMBINED":
        combined_report_note = """
                                <p style="color: #333333; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                    This attachment combines the P1 potential analysis with the VDA 6.3 sections in one report.
                                </p>
        """
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #f4f4f4;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: #f4f4f4; padding: 20px;">
            <tr>
                <td align="center">
                    <table width="600" cellpadding="0" cellspacing="0" border="0" style="background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                        <!-- Header -->
                        <tr>
                            <td style="background: linear-gradient(135deg, #1e3a8a 0%, #1e40af 100%); padding: 40px 30px; text-align: center;">
                                <h1 style="color: #ffffff; margin: 0; font-size: 28px; font-weight: bold;">
                                    Audit Report Available
                                </h1>
                                <p style="color: #ffffff; margin: 10px 0 0 0; font-size: 14px; opacity: 0.9;">
                                    {audit_data.get('audit_number', 'N/A')}
                                </p>
                            </td>
                        </tr>
                        
                        <!-- Content -->
                        <tr>
                            <td style="padding: 40px 30px;">
                                <p style="color: #333333; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                    Hello,
                                </p>
                                
                                <p style="color: #333333; font-size: 16px; line-height: 1.6; margin: 0 0 30px 0;">
                                    The audit report for <strong>{audit_data.get('audit_number', 'N/A')}</strong> 
                                    has been completed and is attached to this email.
                                </p>
                                {combined_report_note}
                                
                                {custom_msg_html}
                                
                                <!-- Audit Details -->
                                <table width="100%" cellpadding="10" cellspacing="0" border="0" style="background-color: #f8f9fa; border-radius: 8px; margin: 20px 0;">
                                    <tr>
                                        <td style="padding: 20px;">
                                            <h3 style="color: #495057; margin: 0 0 15px 0; font-size: 16px; font-weight: bold;">
                                                Audit Summary
                                            </h3>
                                            <table width="100%" cellpadding="5" cellspacing="0" border="0">
                                                <tr>
                                                    <td style="color: #6c757d; font-size: 14px; padding: 5px 0;">
                                                        <strong>Auditor:</strong>
                                                    </td>
                                                    <td style="color: #495057; font-size: 14px; padding: 5px 0; text-align: right;">
                                                        {audit_data.get('auditor', 'N/A')}
                                                    </td>
                                                </tr>
                                                <tr>
                                                    <td style="color: #6c757d; font-size: 14px; padding: 5px 0;">
                                                        <strong>Plant:</strong>
                                                    </td>
                                                    <td style="color: #495057; font-size: 14px; padding: 5px 0; text-align: right;">
                                                        {audit_data.get('plant', 'N/A')}
                                                    </td>
                                                </tr>
  {sector_row}
                                                <tr>
                                                    <td style="color: #6c757d; font-size: 14px; padding: 5px 0;">
                                                        <strong>Audit Date:</strong>
                                                    </td>
                                                    <td style="color: #495057; font-size: 14px; padding: 5px 0; text-align: right;">
                                                        {audit_data.get('audit_date', 'N/A')}
                                                    </td>
                                                </tr>
                                                {score_row}
                                            </table>
                                        </td>
                                    </tr>
                                </table>
                                
                                <p style="color: #666666; font-size: 14px; line-height: 1.6; margin: 30px 0 0 0;">
                                    Please find the complete audit report attached as a PDF file. 
                                    If you have any questions or need clarification, please don't hesitate to reach out.
                                </p>
                            </td>
                        </tr>
                        
                        <!-- Footer -->
                        <tr>
                            <td style="background-color: #f8f9fa; padding: 20px 30px; text-align: center; border-top: 1px solid #e9ecef;">
                                <p style="color: #6c757d; font-size: 12px; margin: 0; line-height: 1.5;">
                                    This is an automated message from the Audit Management System.<br>
                                    Please do not reply to this email.
                                </p>
                                <p style="color: #adb5bd; font-size: 11px; margin: 10px 0 0 0;">
                                    © {datetime.now().year} Audit Management System. All rights reserved.
                                </p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """
    
    return html
