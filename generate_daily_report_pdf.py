import os
import sys
import datetime

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

def create_daily_report_pdf(filename="Daily_IT_Support_Master_Report_Sample.pdf"):
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    # Colors
    NAVY = colors.HexColor("#1A365D")
    TEAL = colors.HexColor("#0D9488")
    DARK_GRAY = colors.HexColor("#2D3748")
    LIGHT_BG = colors.HexColor("#F7FAFC")
    BORDER_COLOR = colors.HexColor("#CBD5E0")
    GREEN_BG = colors.HexColor("#DCFCE7")
    YELLOW_BG = colors.HexColor("#FEF08A")
    BLUE_BG = colors.HexColor("#DBEAFE")

    # Custom Styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=NAVY,
        spaceAfter=2
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=TEAL,
        spaceAfter=12
    )

    heading2_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        textColor=NAVY,
        spaceBefore=10,
        spaceAfter=6
    )

    body_style = ParagraphStyle(
        'BodyTextCustom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=DARK_GRAY
    )

    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=colors.white
    )

    table_body_style = ParagraphStyle(
        'TableBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        textColor=DARK_GRAY
    )

    table_body_bold = ParagraphStyle(
        'TableBodyBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=DARK_GRAY
    )

    story = []

    # Title & Header
    today_str = datetime.datetime.now().strftime("%d %B %Y")
    story.append(Paragraph("DAILY IT & FACILITIES SUPPORT MASTER REPORT", title_style))
    story.append(Paragraph(f"EXECUTIVE SUMMARY & TICKET AUDIT TRAIL | DATE: {today_str.upper()}", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=2, color=NAVY, spaceAfter=12))

    # Executive Overview Metric Cards Table
    story.append(Paragraph("1. Executive Summary Overview", heading2_style))
    summary_data = [
        [
            Paragraph("Total Tickets Today", table_header_style),
            Paragraph("Tickets Resolved / Closed", table_header_style),
            Paragraph("Tickets In Progress", table_header_style),
            Paragraph("Open / Pending Tickets", table_header_style),
        ],
        [
            Paragraph("<font size=16 color='#1A365D'><b>4</b></font>", table_body_bold),
            Paragraph("<font size=16 color='#15803D'><b>2</b></font> (50%)", table_body_bold),
            Paragraph("<font size=16 color='#1D4ED8'><b>1</b></font> (25%)", table_body_bold),
            Paragraph("<font size=16 color='#A16207'><b>1</b></font> (25%)", table_body_bold),
        ]
    ]
    summary_table = Table(summary_data, colWidths=[135, 135, 135, 135])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), NAVY),
        ('BACKGROUND', (0,1), (-1,1), LIGHT_BG),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('PADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 12))

    # Support Admin Performance Table
    story.append(Paragraph("2. Support Admin Performance & Breakdown", heading2_style))
    admin_perf_data = [
        [
            Paragraph("Support Admin Name", table_header_style),
            Paragraph("Contact Phone", table_header_style),
            Paragraph("Assigned Category", table_header_style),
            Paragraph("Assigned Today", table_header_style),
            Paragraph("Resolved / Closed", table_header_style),
            Paragraph("Pending", table_header_style),
        ],
        [
            Paragraph("<b>Kevin Chikati</b>", table_body_style),
            Paragraph("+263 718 627 526", table_body_style),
            Paragraph("Computers, Wi-Fi & Routers", table_body_style),
            Paragraph("2", table_body_style),
            Paragraph("<font color='#15803D'><b>1</b></font>", table_body_bold),
            Paragraph("1", table_body_style),
        ],
        [
            Paragraph("<b>Ellias Murenga</b>", table_body_style),
            Paragraph("+263 788 843 579", table_body_style),
            Paragraph("Printers, Scanners & LAN", table_body_style),
            Paragraph("1", table_body_style),
            Paragraph("<font color='#15803D'><b>1</b></font>", table_body_bold),
            Paragraph("0", table_body_style),
        ],
        [
            Paragraph("<b>Faisal Kassim</b>", table_body_style),
            Paragraph("+263 780 100 503", table_body_style),
            Paragraph("Phones, CCTV, Power & Facilities", table_body_style),
            Paragraph("1", table_body_style),
            Paragraph("<font color='#15803D'><b>0</b></font>", table_body_bold),
            Paragraph("1", table_body_style),
        ],
        [
            Paragraph("<b>TOTALS</b>", table_header_style),
            Paragraph("-", table_header_style),
            Paragraph("All Categories", table_header_style),
            Paragraph("<b>4</b>", table_header_style),
            Paragraph("<b>2</b>", table_header_style),
            Paragraph("<b>2</b>", table_header_style),
        ],
    ]

    admin_perf_table = Table(admin_perf_data, colWidths=[100, 95, 145, 65, 70, 65])
    admin_perf_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), NAVY),
        ('BACKGROUND', (0,-1), (-1,-1), TEAL),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('PADDING', (0,0), (-1,-1), 6),
        ('ROWBACKGROUNDS', (0,1), (-1,-2), [colors.white, LIGHT_BG])
    ]))
    story.append(admin_perf_table)
    story.append(Spacer(1, 12))

    # Itemized Ticket Audit Trail Table
    story.append(Paragraph("3. Itemized Ticket Log Audit Trail", heading2_style))
    ticket_log_data = [
        [
            Paragraph("Ticket ID", table_header_style),
            Paragraph("Employee & Dept", table_header_style),
            Paragraph("Category & Issue", table_header_style),
            Paragraph("Priority", table_header_style),
            Paragraph("Assigned Admin", table_header_style),
            Paragraph("Status", table_header_style),
        ],
        [
            Paragraph("<b>TKT-20260817-00001</b>", table_body_bold),
            Paragraph("Chaleka Stuart<br/><font color='#718096'>Sales (110 Coventry)</font>", table_body_style),
            Paragraph("Computers & Laptops<br/><i>Display / Screen flickering</i>", table_body_style),
            Paragraph("<font color='#C53030'><b>High</b></font>", table_body_style),
            Paragraph("Kevin Chikati", table_body_style),
            Paragraph("<font color='#15803D'><b>Resolved</b></font>", table_body_style),
        ],
        [
            Paragraph("<b>TKT-20260817-00002</b>", table_body_bold),
            Paragraph("David Nyandare<br/><font color='#718096'>Shop Mgr (110 Coventry)</font>", table_body_style),
            Paragraph("Printers & Scanners<br/><i>Paper jam in tray 2</i>", table_body_style),
            Paragraph("Medium", table_body_style),
            Paragraph("Ellias Murenga", table_body_style),
            Paragraph("<font color='#15803D'><b>Closed</b></font>", table_body_style),
        ],
        [
            Paragraph("<b>TKT-20260817-00003</b>", table_body_bold),
            Paragraph("Esmatullah Wais<br/><font color='#718096'>Warehouse (110 Coventry)</font>", table_body_style),
            Paragraph("Security & Access<br/><i>CCTV camera 4 offline</i>", table_body_style),
            Paragraph("<font color='#C53030'><b>Urgent</b></font>", table_body_style),
            Paragraph("Faisal Kassim", table_body_style),
            Paragraph("<font color='#1D4ED8'><b>In Progress</b></font>", table_body_style),
        ],
        [
            Paragraph("<b>TKT-20260817-00004</b>", table_body_bold),
            Paragraph("Zayn<br/><font color='#718096'>General (110 Coventry)</font>", table_body_style),
            Paragraph("Networking & Wi-Fi<br/><i>Wi-Fi password prompt loop</i>", table_body_style),
            Paragraph("Medium", table_body_style),
            Paragraph("Kevin Chikati", table_body_style),
            Paragraph("<font color='#A16207'><b>Open</b></font>", table_body_style),
        ],
    ]

    ticket_log_table = Table(ticket_log_data, colWidths=[100, 110, 130, 50, 80, 70])
    ticket_log_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), NAVY),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('PADDING', (0,0), (-1,-1), 6),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, LIGHT_BG])
    ]))
    story.append(ticket_log_table)

    story.append(Spacer(1, 15))
    footer_p = Paragraph("<font color='#718096'><b>Executive IT Operations & Support Analytics</b> | Confidential Daily Report</font>", ParagraphStyle('FooterStyle', parent=styles['Normal'], alignment=1, fontSize=8))
    story.append(footer_p)

    doc.build(story)
    print(f"PDF Daily Report successfully generated: {filename}")

if __name__ == "__main__":
    create_daily_report_pdf()
