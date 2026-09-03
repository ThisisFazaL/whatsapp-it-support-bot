import os
import sys
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas to dynamically compute and render total page numbers."""
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

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#475569"))
        
        # Header banner on pages > 1
        if self._pageNumber > 1:
            self.drawString(54, 11 * 72 - 36, "BUILDING PROJECTS SUPPORT CHATBOT — EMPLOYEE OPERATIONAL GUIDE")
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.5)
            self.line(54, 11 * 72 - 42, 8.5 * 72 - 54, 11 * 72 - 42)
        
        # Footer
        footer_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(8.5 * 72 - 54, 36, footer_text)
        self.drawString(54, 36, "CONFIDENTIAL & PROPRIETARY — INTERNAL OPERATIONAL MANUAL")
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(54, 48, 8.5 * 72 - 54, 48)
        self.restoreState()

def build_pdf(filename):
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#0F172A'),
        alignment=TA_LEFT,
        spaceAfter=4
    )

    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10.5,
        leading=14,
        textColor=colors.HexColor('#0284C7'),
        alignment=TA_LEFT,
        spaceAfter=10
    )

    h1_style = ParagraphStyle(
        'SectionH1',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12.5,
        leading=16,
        textColor=colors.HexColor('#0F172A'),
        spaceBefore=10,
        spaceAfter=5,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        'BodyDark',
        parent=styles['BodyText'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=13,
        textColor=colors.HexColor('#334155'),
        alignment=TA_LEFT,
        spaceAfter=4
    )

    bullet_style = ParagraphStyle(
        'BulletText',
        parent=body_style,
        leftIndent=10,
        bulletIndent=3,
        spaceAfter=3
    )

    callout_style = ParagraphStyle(
        'CalloutText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12.5,
        textColor=colors.HexColor('#0F172A'),
        alignment=TA_LEFT
    )

    hazard_callout_style = ParagraphStyle(
        'HazardText',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=12.5,
        textColor=colors.HexColor('#991B1B'),
        alignment=TA_LEFT
    )

    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10.5,
        textColor=colors.white,
        alignment=TA_LEFT
    )

    table_cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#1E293B'),
        alignment=TA_LEFT
    )

    question_style = ParagraphStyle(
        'QStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=11.5,
        textColor=colors.HexColor('#0369A1')
    )

    story = []

    # Title & Header Banner
    story.append(Paragraph("Building Projects Support Chatbot", title_style))
    story.append(Paragraph("Employee Operational Guide, Automated Flow & Staff Feedback Review", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#0284C7'), spaceAfter=10))

    # Executive Overview Box
    overview_text = (
        "<b>PURPOSE & DUAL-ROLE REPORTERS:</b> All team members authorized to log Building Projects tickets "
        "(including <b>Paidamoyo Mapeka (Paida), Simbarashe Chaunoita (Simbah), Soyab Patel, Batsirai Muradzikwa (Batsi), Fazal, Arif, Zayn, and Faizan Patel</b>) are registered as "
        "<b>Dual-Role Users</b>.<br/><br/>"
        "🔀 <b>DUAL-DOMAIN SELECTION:</b> When an authorized reporter messages the chatbot, they automatically receive two "
        "interactive buttons to choose which type of ticket they need:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;• <code>[ 💻 IT Support ]</code> — Opens IT Support categories directly (computers, network, printers, software).<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;• <code>[ 🏗️ Projects ]</code> — Opens Building Projects locations (building repairs, plumbing, electrical, doors)."
    )
    callout_table = Table(
        [[Paragraph(overview_text, callout_style)]],
        colWidths=[504]
    )
    callout_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F0F9FF')),
        ('BORDER', (0, 0), (-1, -1), 1, colors.HexColor('#BAE6FD')),
        ('PADDING', (0, 0), (-1, -1), 7),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(callout_table)
    story.append(Spacer(1, 8))

    # Section 1: User Routing & Entry Behavior
    story.append(Paragraph("1. User Access & Automated Workflow Entry", h1_style))
    story.append(Paragraph(
        "When messaging <b>'hi'</b>, <b>'menu'</b>, or <b>'raise ticket'</b> to our official WhatsApp bot, your registered role determines your experience:",
        body_style
    ))

    entry_data = [
        [Paragraph("<b>User Registration Role</b>", table_header_style), Paragraph("<b>Automated Entry Behavior on WhatsApp</b>", table_header_style)],
        [Paragraph("<b>Authorized Projects Reporters</b><br/><i>(Paida, Fazal, Arif, Zayn, Faizan Patel)</i>", table_cell_style), Paragraph("<b>🔀 Dual-Role Buttons:</b> Receives interactive domain selection buttons:<br/>• <code>[ 💻 IT Support ]</code> — Skips locations, opens IT categories.<br/>• <code>[ 🏗️ Projects ]</code> — Opens Building Projects site locations.", table_cell_style)],
        [Paragraph("<b>Support Admins</b><br/><i>(Master Admin & Facilities Admins)</i>", table_cell_style), Paragraph("<b>🔀 Full Portal & Dual Access:</b> Receives domain buttons plus Admin Dashboard options (View Assigned, Summary Reports).", table_cell_style)],
        [Paragraph("<b>Standard IT Staff</b><br/><i>(Office Employees)</i>", table_cell_style), Paragraph("<b>💻 Direct IT Flow:</b> Bypasses locations entirely. Opens IT Support categories directly.", table_cell_style)],
    ]
    entry_table = Table(entry_data, colWidths=[160, 344])
    entry_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F172A')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
    ]))
    story.append(entry_table)
    story.append(Spacer(1, 8))

    # Section 2: Step-by-Step Projects Creation Flow
    story.append(Paragraph("2. Step-by-Step Building Projects Ticket Flow", h1_style))

    steps_list = [
        "<b>Step 1: Select Site Location</b> — Choose from our official 7 site locations by replying with the corresponding number:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;1. <b>Tagoneswa Hardware</b> &nbsp;&nbsp;|&nbsp;&nbsp; 2. <b>LG Plast</b> &nbsp;&nbsp;|&nbsp;&nbsp; 3. <b>Shop 5</b> &nbsp;&nbsp;|&nbsp;&nbsp; 4. <b>Shop 6</b><br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;5. <b>Kreckle Foods</b> &nbsp;&nbsp;|&nbsp;&nbsp; 6. <b>19 Mcloughlin Kensington</b> &nbsp;&nbsp;|&nbsp;&nbsp; 7. <b>12 Divine Milton Park</b><br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;8. <i>Other (Type location)</i>",

        "<b>Step 2: Specify Room / Area</b> — Type the specific location within the site.<br/>"
        "<i>Examples: 'Main Entrance Door', 'Executive Kitchen', 'Warehouse Bay 3', 'Restroom 2nd Floor'.</i>",

        "<b>Step 3: Select Category & Specific Issue</b> — Select from 6 facility category groups:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;• <b>Doors, Windows & Locks</b> (Latches, Hinges, Glass, Blinds)<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;• <b>Ceiling, Walls & Roofing</b> (Leaks, Tiles, Paint, Drywall)<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;• <b>Electrical & Lighting</b> (LED Flickering, Sockets, Wiring, Breakers)<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;• <b>Plumbing & Water Leakage</b> (Taps, Flushes, Drains, Dispensers)<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;• <b>General Building & Furniture</b> (Office Chairs, Desks, Cabinets, AC/HVAC)<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;• <b>Renovation & Expansion</b> (New Floor, Structural Partitions, Flooring/Tiling, Wiring & Plumbing Fittings)",

        "<b>Step 4: Describe Issue & Optional Photo</b> — Type a brief description and optionally attach a photo of the defect in WhatsApp.",

        "<b>Step 5: Select Priority Level & Safety Hazard Flag</b> — Select urgency (`Low`, `Medium`, `High`, `Urgent / Safety Hazard`). Marking a ticket as an urgent Safety Hazard triggers immediate emergency escalation."
    ]

    for step_text in steps_list:
        story.append(Paragraph(f"• {step_text}", bullet_style))

    story.append(Spacer(1, 6))

    # SAFETY HAZARD HIGHLIGHT BOX (NEW)
    hazard_text = (
        "⚠️ <b>SAFETY HAZARD ESCALATION PROTOCOL:</b><br/>"
        "If a ticket involves a critical safety hazard (such as exposed electrical wires, major water pipe bursts, structural ceiling collapses, or gas leaks), the chatbot flags it with a prominent <b>⚠️ URGENT SAFETY HAZARD FLAG</b>.<br/>"
        "An immediate high-priority alert is dispatched via WhatsApp to the Master Admin (Fazal Saiyed), Facilities Admins (Stanclea & Omar Arizai), and Executive Observers for rapid emergency intervention."
    )
    hazard_table = Table([[Paragraph(hazard_text, hazard_callout_style)]], colWidths=[504])
    hazard_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#FEF2F2')),
        ('BORDER', (0, 0), (-1, -1), 1, colors.HexColor('#FCA5A5')),
        ('PADDING', (0, 0), (-1, -1), 7),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(hazard_table)
    story.append(Spacer(1, 10))

    # Section 3: Admin Resolution & Employee Confirmation
    story.append(Paragraph("3. Admin Resolution & 2-Step Employee Confirmation", h1_style))
    story.append(Paragraph(
        "Every Building Projects ticket undergoes a 2-step verification before formal closure:",
        body_style
    ))

    flow_box_data = [
        [
            Paragraph("<b>STAGE 1: MANDATORY ADMIN RESOLUTION NOTE</b>", ParagraphStyle('H1Box', parent=table_header_style, textColor=colors.HexColor('#0284C7'))),
            Paragraph("When the facilities admin (Stanclea or Omar Arizai) completes repair work on site, they tap <b>[ 🟢 Resolve Ticket ]</b>. The chatbot requires them to submit a mandatory note detailing what was done (e.g., <i>'Replaced cabinet hinge screws, aligned door, and tested latch'</i>).", table_cell_style)
        ],
        [
            Paragraph("<b>STAGE 2: EMPLOYEE CONFIRMATION BUTTONS</b>", ParagraphStyle('H2Box', parent=table_header_style, textColor=colors.HexColor('#0F172A'))),
            Paragraph("The reporter receives the resolution note on WhatsApp with two interactive buttons:<br/>"
                      "• <b>[ ✅ Confirm & Close ]</b>: Formally marks ticket as <b>CLOSED</b> and alerts executive management.<br/>"
                      "• <b>[ 🔄 Reopen Ticket ]</b>: Reverts ticket status to <b>OPEN</b> if additional work is required.", table_cell_style)
        ]
    ]
    flow_box_table = Table(flow_box_data, colWidths=[160, 344])
    flow_box_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#E0F2FE')),
        ('BACKGROUND', (0, 1), (0, 1), colors.HexColor('#F1F5F9')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(flow_box_table)
    story.append(Spacer(1, 10))

    # Section 4: Staff Feedback, Validation & Review Questions
    story.append(Paragraph("4. Staff Feedback, Validation & Review Questions", h1_style))
    story.append(Paragraph(
        "To ensure this workflow fits your daily operational needs perfectly, please review the following questions and share your feedback with management:",
        body_style
    ))

    q_data = [
        [Paragraph("<b>#</b>", table_header_style), Paragraph("<b>Operational Validation Question for Staff & Management</b>", table_header_style), Paragraph("<b>Target Feedback Focus</b>", table_header_style)],
        [
            Paragraph("<b>Q1</b>", question_style),
            Paragraph("<b>Locations Coverage:</b> Are the 7 designated site locations (<i>Tagoneswa Hardware, LG Plast, Shop 5, Shop 6, Kreckle Foods, 19 Mcloughlin Kensington, 12 Divine Milton Park</i>) complete and accurate for your daily facility reporting?", table_cell_style),
            Paragraph("Confirms all physical sites & shops are covered.", table_cell_style)
        ],
        [
            Paragraph("<b>Q2</b>", question_style),
            Paragraph("<b>Dual-Domain Selection:</b> Is having the choice between IT Support and Building Projects via buttons (for reporters like Paida, Fazal, Arif, Zayn, Faizan) clear and easy to navigate on WhatsApp?", table_cell_style),
            Paragraph("Evaluates dual-role button usability.", table_cell_style)
        ],
        [
            Paragraph("<b>Q3</b>", question_style),
            Paragraph("<b>Safety Hazard Escalation:</b> Is the Safety Hazard flag clear? Do emergency issues get flagged fast enough for immediate site safety?", table_cell_style),
            Paragraph("Validates emergency hazard protocol.", table_cell_style)
        ],
        [
            Paragraph("<b>Q4</b>", question_style),
            Paragraph("<b>Resolution Note & Confirmation:</b> Is the 2-step resolution note and confirmation process clear? Does receiving the Admin's resolution note help verify work quality?", table_cell_style),
            Paragraph("Validates quality control & transparency.", table_cell_style)
        ],
        [
            Paragraph("<b>Q5</b>", question_style),
            Paragraph("<b>Categories & Issues:</b> Are there any additional building categories, subcategories, or specific repair issue types that should be added to the chatbot list?", table_cell_style),
            Paragraph("Identifies missing repair options or issue types.", table_cell_style)
        ],
        [
            Paragraph("<b>Q6</b>", question_style),
            Paragraph("<b>User Access & Reporters:</b> Are there any additional site managers, supervisors, or maintenance staff members who should be granted ticket creation access?", table_cell_style),
            Paragraph("Gathers list of new staff to authorize.", table_cell_style)
        ]
    ]
    q_table = Table(q_data, colWidths=[28, 336, 140])
    q_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0369A1')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('PADDING', (0, 0), (-1, -1), 5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(q_table)
    story.append(Spacer(1, 10))

    # Key Contacts Summary Table
    story.append(Paragraph("5. System Roles & Key Contacts Directory", h1_style))

    roles_data = [
        [Paragraph("<b>Role / Title</b>", table_header_style), Paragraph("<b>Name / Contacts</b>", table_header_style), Paragraph("<b>Responsibility</b>", table_header_style)],
        [Paragraph("<b>Master Support Admin</b>", table_cell_style), Paragraph("Fazal Saiyed<br/><code>+91 92653 68695</code>", table_cell_style), Paragraph("Overall System Admin & Executive Oversight", table_cell_style)],
        [Paragraph("<b>Projects Support Admin</b>", table_cell_style), Paragraph("Stanclea<br/><code>+263 78009 9291</code>", table_cell_style), Paragraph("On-site Facilities & Building Projects Lead", table_cell_style)],
        [Paragraph("<b>Projects Support Admin</b>", table_cell_style), Paragraph("Omar Arizai<br/><code>+263 77 133 3602</code>", table_cell_style), Paragraph("On-site Facilities & Maintenance Lead", table_cell_style)],
        [Paragraph("<b>Authorized Reporters</b>", table_cell_style), Paragraph("Stanclea, Omar Arizai, Paidamoyo Mapeka (Paida), Simbarashe Chaunoita (Simbah), Soyab Patel, Batsirai Muradzikwa (Batsi), Fazal S., Arif, Zayn, Faizan Patel", table_cell_style), Paragraph("Dual-Role Users (Can log both IT & Project Tickets)", table_cell_style)],
    ]
    roles_table = Table(roles_data, colWidths=[130, 174, 200])
    roles_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F172A')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('PADDING', (0, 0), (-1, -1), 5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
    ]))
    story.append(roles_table)
    story.append(Spacer(1, 10))

    # Sign-off box
    signoff_text = "<b>FEEDBACK & NEW USER REGISTRATION:</b> Share your responses to the Review Questions above with Master Admin (Fazal Saiyed) on WhatsApp to update repair categories or authorize new team members."
    signoff_table = Table([[Paragraph(signoff_text, ParagraphStyle('SO', parent=table_cell_style, fontSize=8.5, textColor=colors.HexColor('#1E293B')))]], colWidths=[504])
    signoff_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('BORDER', (0, 0), (-1, -1), 1, colors.HexColor('#0284C7')),
        ('PADDING', (0, 0), (-1, -1), 7),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    story.append(signoff_table)

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Generated PDF guide at: {filename}")

if __name__ == "__main__":
    out_dir = r"C:\Users\nytfa\.gemini\antigravity\brain\a0e0a826-9832-46c9-98cc-3254d062f649"
    os.makedirs(out_dir, exist_ok=True)
    pdf_path = os.path.join(out_dir, "Building_Projects_Support_Workflow_Employee_Guide.pdf")
    build_pdf(pdf_path)
