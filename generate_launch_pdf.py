import os
import sys

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.units import inch
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "reportlab"])
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.units import inch

def create_launch_pdf(filename="Support_Chatbot_Launch_Guide.pdf"):
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()

    # Colors
    NAVY = colors.HexColor("#1A365D")
    TEAL = colors.HexColor("#0D9488")
    DARK_GRAY = colors.HexColor("#2D3748")
    LIGHT_BG = colors.HexColor("#F7FAFC")
    BORDER_COLOR = colors.HexColor("#E2E8F0")

    # Custom Styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=22,
        leading=26,
        textColor=NAVY,
        spaceAfter=4
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=TEAL,
        spaceAfter=15
    )

    heading2_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        textColor=NAVY,
        spaceBefore=12,
        spaceAfter=8
    )

    body_style = ParagraphStyle(
        'BodyTextCustom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=14,
        textColor=DARK_GRAY
    )

    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=colors.white
    )

    table_body_style = ParagraphStyle(
        'TableBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=DARK_GRAY
    )

    story = []

    # Title & Header
    story.append(Paragraph("SUPPORT CHATBOT", title_style))
    story.append(Paragraph("OFFICIAL WHATSAPP CHATBOT LAUNCH & USER GUIDE | EFFECTIVE 17 AUGUST 2026", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=2, color=NAVY, spaceAfter=15))

    # Executive Announcement Box
    announcement_text = """
    <b>Dear Team,</b><br/><br/>
    We are pleased to announce the official launch of our automated <b>WhatsApp IT & Facilities Support Chatbot</b>, effective <b>Monday, 17th August 2026</b>.<br/>
    All team members can now log hardware, software, network, printer, security, power, and facilities requests directly via WhatsApp 24x7. Each request is automatically routed to the designated Support Administrator for fast resolution.
    """
    box_table = Table([[Paragraph(announcement_text, body_style)]], colWidths=[532])
    box_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), LIGHT_BG),
        ('BOX', (0,0), (-1,-1), 1, TEAL),
        ('PADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(box_table)
    story.append(Spacer(1, 15))

    # Quick Access Box
    access_data = [
        [Paragraph("<b>OFFICIAL WHATSAPP SUPPORT NUMBER:</b>", table_header_style), Paragraph("<b>+91 93282 95424</b>", table_header_style)],
        [Paragraph("<b>CONTACT NAME TO SAVE:</b>", table_body_style), Paragraph("Support Chatbot", table_body_style)],
        [Paragraph("<b>DIRECT CHAT LINK:</b>", table_body_style), Paragraph("https://wa.me/919328295424?text=Hi", table_body_style)],
        [Paragraph("<b>AVAILABILITY:</b>", table_body_style), Paragraph("Active 24 Hours / 7 Days a Week", table_body_style)],
    ]
    access_table = Table(access_data, colWidths=[200, 332])
    access_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (1,0), NAVY),
        ('BACKGROUND', (0,1), (-1,-1), colors.white),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(access_table)
    story.append(Spacer(1, 15))

    # Scope of Support Services Table
    story.append(Paragraph("1. Scope of Support Services", heading2_style))
    
    scope_data = [
        [Paragraph("Category", table_header_style), Paragraph("Subcategories Covered", table_header_style), Paragraph("Example Issues Covered", table_header_style)],
        
        [Paragraph("<b>1. IT & Computing Equipment</b>", table_body_style), 
         Paragraph("• Computer & Laptop<br/>• Printers & Scanners<br/>• Desk Phone & Landline<br/>• Other IT Equipment", table_body_style),
         Paragraph("PC troubleshooting, Windows OS, software activation, Canon/POS printer maintenance, paper jam, toner, PBX intercom cabling.", table_body_style)],

        [Paragraph("<b>2. Networking & Connectivity</b>", table_body_style), 
         Paragraph("• Wi-Fi & Wireless Network<br/>• LAN & Wired Ethernet<br/>• Internet & Routers<br/>• Other Network Issue", table_body_style),
         Paragraph("Wireless connectivity, password loop, LAN cabling, RJ45 termination, MikroTik routers, Starlink, Liquid & ISP coordination.", table_body_style)],

        [Paragraph("<b>3. Security & Access Control</b>", table_body_style), 
         Paragraph("• CCTV & Surveillance<br/>• Biometrics & Attendance<br/>• Gates & Access Control<br/>• Alarms & Security", table_body_style),
         Paragraph("CCTV camera offline, playback errors, fingerprint/face scanner sync, automatic gate barriers, intrusion alarm troubleshooting.", table_body_style)],

        [Paragraph("<b>4. Electrical & Power Systems</b>", table_body_style), 
         Paragraph("• Electrical Fittings & Wiring<br/>• Inverters & UPS Backup<br/>• Solar Power Systems<br/>• Electronics & Power", table_body_style),
         Paragraph("Electrical fault finding, inverter battery systems, Solar PV maintenance, power surge protection, borehole & pump power fault finding.", table_body_style)],

        [Paragraph("<b>5. Facilities & Maintenance</b>", table_body_style), 
         Paragraph("• General Maintenance<br/>• Facilities & Emergency", table_body_style),
         Paragraph("General office facilities maintenance, emergency fault response & servicing.", table_body_style)],
    ]

    scope_table = Table(scope_data, colWidths=[130, 160, 242])
    scope_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), NAVY),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('PADDING', (0,0), (-1,-1), 6),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, LIGHT_BG])
    ]))
    story.append(scope_table)
    story.append(Spacer(1, 15))

    # How to Use Step-by-Step
    story.append(Paragraph("2. How to Raise & Track Support Tickets", heading2_style))
    
    steps_data = [
        [Paragraph("<b>STEP 1: SAVE CONTACT</b>", table_header_style), Paragraph("Save <b>+91 93282 95424</b> as <b>Support Chatbot</b> in your phone contacts.", table_body_style)],
        [Paragraph("<b>STEP 2: START CHAT</b>", table_header_style), Paragraph("Send <b>'Hi'</b> or <b>'Menu'</b> on WhatsApp. The chatbot will recognize your registered profile.", table_body_style)],
        [Paragraph("<b>STEP 3: SELECT CATEGORY</b>", table_header_style), Paragraph("Reply with the number corresponding to your Category, Subcategory, and Issue.", table_body_style)],
        [Paragraph("<b>STEP 4: ENTER DETAILS</b>", table_header_style), Paragraph("Type a brief description of the problem and optionally attach a photo/screenshot.", table_body_style)],
        [Paragraph("<b>STEP 5: RECEIVE TICKET ID</b>", table_header_style), Paragraph("You will instantly receive your official Ticket ID (e.g., <b>TKT-20260817-00001</b>).", table_body_style)],
        [Paragraph("<b>STEP 6: TRACK TICKETS</b>", table_header_style), Paragraph("Send <b>'My Tickets'</b> anytime to view live updates on all your pending or resolved tickets.", table_body_style)],
    ]
    steps_table = Table(steps_data, colWidths=[140, 392])
    steps_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,-1), TEAL),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(steps_table)
    story.append(Spacer(1, 15))

    # Support Admin Roster
    story.append(Paragraph("3. Support Admin Routing Roster", heading2_style))
    roster_data = [
        [Paragraph("Admin Name", table_header_style), Paragraph("Contact Phone", table_header_style), Paragraph("Assigned Specialization", table_header_style)],
        [Paragraph("<b>Kevin Chikati</b>", table_body_style), Paragraph("+263 718 627 526", table_body_style), Paragraph("Computers, Laptops, Software/Apps, Wi-Fi & Internet Routers", table_body_style)],
        [Paragraph("<b>Ellias Murenga</b>", table_body_style), Paragraph("+263 788 843 579", table_body_style), Paragraph("Printers, Scanners, LAN Cabling & Network Infrastructure", table_body_style)],
        [Paragraph("<b>Faisal Kassim</b>", table_body_style), Paragraph("+263 780 100 503", table_body_style), Paragraph("Desk Phones, CCTV, Biometrics, Access Gates, Alarms, Electrical & Facilities", table_body_style)],
    ]
    roster_table = Table(roster_data, colWidths=[120, 130, 282])
    roster_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), NAVY),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('PADDING', (0,0), (-1,-1), 6),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, LIGHT_BG])
    ]))
    story.append(roster_table)

    story.append(Spacer(1, 20))
    footer_p = Paragraph("<font color='#718096'><b>Support Team & Executive Management</b> | Confidential Internal Document</font>", ParagraphStyle('FooterStyle', parent=styles['Normal'], alignment=1, fontSize=8))
    story.append(footer_p)

    doc.build(story)
    print(f"PDF Launch Guide successfully generated: {filename}")

if __name__ == "__main__":
    create_launch_pdf()
