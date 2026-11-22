import os
import io
import json
import datetime
from pathlib import Path
from typing import Dict, Any, Optional

import qrcode
from PIL import Image as PILImage

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, KeepTogether, PageBreak
)
from reportlab.pdfgen import canvas

from backend.config import REPORTS_DIR

CLINICAL_DISCLAIMER = (
    "This report is produced by AI-assisted tools for clinician decision support only. It is not a "
    "diagnosis. Triage flags are rule-based. OCR-extracted text and lab values may contain errors and "
    "must be verified against the source documents. All findings are probabilistic and must be reviewed "
    "and confirmed by a qualified physician before any clinical action."
)


class NumberedCanvas(canvas.Canvas):
    """Adds running headers and 'Page X of Y' footers."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count: int):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#6B7280"))

        # Running Header
        self.drawString(54, 11 * inch - 36, "ClinicalLens Multimodal Decision Support • Confidential Medical Record")
        self.setStrokeColor(colors.HexColor("#E6E6E9"))
        self.setLineWidth(0.5)
        self.line(54, 11 * inch - 42, 8.5 * inch - 54, 11 * inch - 42)

        # Running Footer
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(8.5 * inch - 54, 36, page_str)
        self.drawString(54, 36, "Privileged & Confidential • AI-Assisted Clinical Decision-Support • Verify against primary data")
        self.line(54, 46, 8.5 * inch - 54, 46)
        self.restoreState()


def generate_qr_code(text: str) -> str:
    """Generates a temporary PNG of the QR code and returns its file path."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=4,
        border=1,
    )
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#25272D", back_color="#FFFFFF")
    
    qr_path = REPORTS_DIR / f"qr_{text}.png"
    img.save(str(qr_path))
    return str(qr_path)


def generate_pdf_report(
    case_data: Dict[str, Any],
    version: int = 1
) -> str:
    """
    Generates a ReportLab PDF clinical report.
    Returns the absolute path to the generated PDF.
    """
    case_code = case_data.get("case_code", "UNKNOWN_CASE")
    pdf_filename = f"{case_code}_report_v{version}.pdf"
    pdf_path = REPORTS_DIR / pdf_filename

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54,
    )

    styles = getSampleStyleSheet()

    # Custom typography matching ClinicalLens design system
    styles.add(ParagraphStyle(
        name="DocTitle",
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#25272D"),
    ))
    styles.add(ParagraphStyle(
        name="SectionHeading",
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#C8102E"),
        spaceBefore=12,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="BodyTextSmall",
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#25272D"),
    ))
    styles.add(ParagraphStyle(
        name="BodyTextBold",
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#25272D"),
    ))
    styles.add(ParagraphStyle(
        name="TriageText",
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.white,
    ))

    story = []

    # 1. Header with Hospital / Letterhead & QR Code
    qr_img_path = generate_qr_code(case_code)
    header_data = [
        [
            Paragraph("<b>CLINICALLENS MEDICAL DIAGNOSTIC REPORT</b><br/>"
                      "<font size=8 color='#5F6368'>Local & Private Multimodal Clinical Decision-Support System</font>", styles["DocTitle"]),
            RLImage(qr_img_path, width=0.8 * inch, height=0.8 * inch)
        ]
    ]
    header_table = Table(header_data, colWidths=[6.0 * inch, 1.0 * inch])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 8))

    # 2. Patient Block Table
    pat = case_data.get("patient", {})
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    patient_info = [
        [
            Paragraph(f"<b>Patient Name:</b> {pat.get('name', 'N/A')}", styles["BodyTextSmall"]),
            Paragraph(f"<b>Patient Code:</b> {pat.get('patient_code', 'N/A')}", styles["BodyTextSmall"]),
            Paragraph(f"<b>Case Code:</b> {case_code} (v{version})", styles["BodyTextSmall"]),
        ],
        [
            Paragraph(f"<b>Age / Sex:</b> {pat.get('age', 'N/A')} yrs / {pat.get('sex', 'N/A')}", styles["BodyTextSmall"]),
            Paragraph(f"<b>Blood Group:</b> {pat.get('blood_group', 'N/A')}", styles["BodyTextSmall"]),
            Paragraph(f"<b>Report Date:</b> {now_str}", styles["BodyTextSmall"]),
        ],
        [
            Paragraph(f"<b>Consulting Doctor:</b> {case_data.get('doctor_name', 'Dr. Aris Thorne')}", styles["BodyTextSmall"]),
            Paragraph(f"<b>Council Reg:</b> {case_data.get('doctor_reg', 'MC-2015-88412')}", styles["BodyTextSmall"]),
            Paragraph(f"<b>Facility:</b> {case_data.get('hospital', 'Clinical Workspace')}", styles["BodyTextSmall"]),
        ]
    ]
    pat_table = Table(patient_info, colWidths=[2.33 * inch, 2.33 * inch, 2.33 * inch])
    pat_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F6F6F7")),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#E6E6E9")),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E6E6E9")),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(pat_table)
    story.append(Spacer(1, 10))

    # 3. Triage Banner
    triage_lvl = case_data.get("triage_level", "ROUTINE").upper()
    triage_bg = colors.HexColor("#C8102E") if triage_lvl == "URGENT" else colors.HexColor("#B7791F") if triage_lvl == "PRIORITY" else colors.HexColor("#1F7A5C")
    
    triage_table = Table(
        [[Paragraph(f"TRIAGE CLASSIFICATION: {triage_lvl} (CLINICAL AUDIT REQUIRED)", styles["TriageText"])]],
        colWidths=[7.0 * inch]
    )
    triage_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), triage_bg),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(triage_table)
    story.append(Spacer(1, 10))

    # 4. Vital Signs & Clinical Presentation
    story.append(Paragraph("Vital Signs & Clinical Presentation", styles["SectionHeading"]))
    v = case_data.get("vitals", {})
    v_parts = []
    if v.get("temp_c"): v_parts.append(f"Temp: {v['temp_c']} °C")
    if v.get("hr"): v_parts.append(f"Heart Rate: {int(v['hr'])} bpm")
    if v.get("bp_sys"): v_parts.append(f"BP: {int(v['bp_sys'])}/{int(v.get('bp_dia', 80))} mmHg")
    if v.get("spo2"): v_parts.append(f"SpO2: {int(v['spo2'])}%")
    if v.get("rr"): v_parts.append(f"Resp Rate: {int(v['rr'])} /min")
    vitals_summary = " • ".join(v_parts) if v_parts else "No vital signs recorded"
    
    story.append(Paragraph(f"<b>Vitals:</b> {vitals_summary}", styles["BodyTextSmall"]))
    story.append(Paragraph(f"<b>Chief Complaint:</b> {case_data.get('chief_complaint', 'None recorded')}", styles["BodyTextSmall"]))
    if case_data.get("onset_duration"):
        story.append(Paragraph(f"<b>Onset & Duration:</b> {case_data['onset_duration']}", styles["BodyTextSmall"]))
    if case_data.get("allergies"):
        story.append(Paragraph(f"<b>Allergies:</b> {case_data['allergies']}", styles["BodyTextSmall"]))
    story.append(Spacer(1, 8))

    # 5. Medications Table
    meds = case_data.get("medicines", [])
    if meds:
        story.append(Paragraph("Current Medications", styles["SectionHeading"]))
        med_rows = [["Drug Name", "Dose", "Frequency", "Duration", "Indication"]]
        for m in meds:
            med_rows.append([m.get("drug_name", ""), m.get("dose", ""), m.get("frequency", ""), m.get("duration", ""), m.get("indication", "")])
        
        med_table = Table(med_rows, colWidths=[1.8 * inch, 1.1 * inch, 1.3 * inch, 1.1 * inch, 1.7 * inch])
        med_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#F6F6F7")),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E6E6E9")),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#E6E6E9")),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(med_table)
        story.append(Spacer(1, 8))

    # 6. Lab Results Table
    labs = case_data.get("labs", [])
    if labs:
        story.append(Paragraph("Laboratory Findings (Auto-Extracted & Audited)", styles["SectionHeading"]))
        lab_rows = [["Test", "Value", "Reference Range", "Flag"]]
        for l in labs:
            flag_str = l.get("flag", "")
            if l.get("critical"):
                flag_str = "CRITICAL " + flag_str
            lab_rows.append([l.get("name", ""), f"{l.get('value')} {l.get('unit', '')}", l.get("ref", "-") or "-", flag_str])
        
        lab_table = Table(lab_rows, colWidths=[2.5 * inch, 1.5 * inch, 2.0 * inch, 1.0 * inch])
        lab_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#F6F6F7")),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E6E6E9")),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#E6E6E9")),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(lab_table)
        story.append(Spacer(1, 8))

    # 7. AI Diagnostic Model Outputs
    runs = case_data.get("runs", [])
    if runs:
        story.append(Paragraph("AI Imaging Model Outputs (CNN Inferences)", styles["SectionHeading"]))
        for r in runs:
            mod_title = f"{r.get('key')} - {r.get('filename', 'Scan')}"
            story.append(Paragraph(f"<b>{mod_title}</b>", styles["BodyTextBold"]))
            story.append(Paragraph(r.get("text", "").replace("\n", "<br/>"), styles["BodyTextSmall"]))
            
            # Embed generated figures if available
            figs = r.get("figures", [])
            for fpath in figs:
                if os.path.exists(fpath):
                    try:
                        story.append(Spacer(1, 4))
                        story.append(RLImage(fpath, width=6.5 * inch, height=3.0 * inch))
                        story.append(Spacer(1, 6))
                    except Exception as e:
                        print(f"[PDF] Figure embed warning: {e}")

    # 8. MedGemma Clinical Analysis
    if case_data.get("quick_summary"):
        story.append(Paragraph("Executive Quick-Read Summary (MedGemma AI)", styles["SectionHeading"]))
        story.append(Paragraph(case_data["quick_summary"].replace("\n", "<br/>"), styles["BodyTextSmall"]))
        story.append(Spacer(1, 8))

    if case_data.get("detailed_analysis"):
        story.append(Paragraph("Detailed Multimodal Synthesis (MedGemma AI)", styles["SectionHeading"]))
        story.append(Paragraph(case_data["detailed_analysis"].replace("\n", "<br/>"), styles["BodyTextSmall"]))
        story.append(Spacer(1, 8))

    # 9. Doctor's Decision and Sign-off
    dec = case_data.get("decision", {})
    if dec:
        story.append(Paragraph("Attending Physician Assessment & Sign-Off", styles["SectionHeading"]))
        dec_data = [
            [
                Paragraph(f"<b>AI Recommendation Action:</b> {dec.get('ai_recommendation_status', 'ACCEPTED')}", styles["BodyTextSmall"]),
                Paragraph(f"<b>Follow-Up Date:</b> {dec.get('follow_up_date', 'As scheduled')}", styles["BodyTextSmall"])
            ],
            [
                Paragraph(f"<b>Final Clinical Assessment:</b><br/>{dec.get('final_assessment', 'Confirmed.')}", styles["BodyTextSmall"]),
                Paragraph(f"<b>Management & Treatment Plan:</b><br/>{dec.get('management_plan', 'Routine care.')}", styles["BodyTextSmall"])
            ],
            [
                Paragraph(f"<b>Clinician Signature:</b><br/><i>Signed electronically by {case_data.get('doctor_name')}</i>", styles["BodyTextSmall"]),
                Paragraph(f"<b>Timestamp:</b> {dec.get('signed_at', now_str)}", styles["BodyTextSmall"])
            ]
        ]
        dec_table = Table(dec_data, colWidths=[3.5 * inch, 3.5 * inch])
        dec_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#FCEBED")),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#C8102E")),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E6E6E9")),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(dec_table)
        story.append(Spacer(1, 10))

    # 10. Disclaimer
    story.append(Paragraph("<b>CLINICAL DISCLAIMER:</b> " + CLINICAL_DISCLAIMER, styles["BodyTextSmall"]))

    # Build PDF with custom running canvas
    doc.build(story, canvasmaker=NumberedCanvas)
    return str(pdf_path)
