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

STATUS_NAMES = {
    1: "Open",
    2: "In Progress",
    3: "Resolved",
    4: "Closed"
}

STATUS_COLORS = {
    1: "#A16207",
    2: "#1D4ED8",
    3: "#15803D",
    4: "#15803D"
}

def resolve_admin_for_ticket(ticket, asg_map):
    """
    Helper function to safely resolve SupportAdmin object from asg_map
    using integer ID, string ID, or prefixed keys.
    """
    if not asg_map or not ticket:
        return None
    
    t_id = getattr(ticket, "ticket_id", None)
    t_num = getattr(ticket, "ticket_number", "")
    
    admin = (
        asg_map.get(t_id)
        or asg_map.get(str(t_id))
        or asg_map.get(f"IT_{t_id}")
        or asg_map.get(f"MAINT_{t_id}")
        or asg_map.get(t_num)
    )
    return admin

def create_daily_report_pdf(filename="Daily_IT_Support_Master_Report_Sample.pdf", today_tickets=None, asg_map=None):
    """
    Generates a dynamic PDF Executive Report built 100% from live database tickets.
    """
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

    # Custom Styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=NAVY,
        spaceAfter=2
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=14,
        textColor=TEAL,
        spaceAfter=10
    )

    heading2_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=15,
        textColor=NAVY,
        spaceBefore=8,
        spaceAfter=5
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
        fontSize=8,
        leading=11,
        textColor=DARK_GRAY
    )

    table_body_bold = ParagraphStyle(
        'TableBodyBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=11,
        textColor=DARK_GRAY
    )

    story = []

    # Title & Header
    today_str = datetime.datetime.now().strftime("%d %B %Y")
    story.append(Paragraph("DAILY IT & FACILITIES SUPPORT MASTER REPORT", title_style))
    story.append(Paragraph(f"EXECUTIVE SUMMARY & TICKET AUDIT TRAIL | DATE: {today_str.upper()}", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=2, color=NAVY, spaceAfter=10))

    if not today_tickets:
        today_tickets = []
    if not asg_map:
        asg_map = {}

    total_count = len(today_tickets)
    open_count = sum(1 for t in today_tickets if t.status_id == 1)
    in_prog_count = sum(1 for t in today_tickets if t.status_id == 2)
    resolved_count = sum(1 for t in today_tickets if t.status_id in (3, 4))

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
            Paragraph(f"<font size=14 color='#1A365D'><b>{total_count}</b></font>", table_body_bold),
            Paragraph(f"<font size=14 color='#15803D'><b>{resolved_count}</b></font> ({int(resolved_count/total_count*100) if total_count else 0}%)", table_body_bold),
            Paragraph(f"<font size=14 color='#1D4ED8'><b>{in_prog_count}</b></font> ({int(in_prog_count/total_count*100) if total_count else 0}%)", table_body_bold),
            Paragraph(f"<font size=14 color='#A16207'><b>{open_count}</b></font> ({int(open_count/total_count*100) if total_count else 0}%)", table_body_bold),
        ]
    ]
    summary_table = Table(summary_data, colWidths=[135, 135, 135, 135])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), NAVY),
        ('BACKGROUND', (0,1), (-1,1), LIGHT_BG),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 10))

    # Support Admin Performance Table
    story.append(Paragraph("2. Support Admin Performance & Breakdown", heading2_style))
    
    admin_stats = {}
    for t in today_tickets:
        admin = resolve_admin_for_ticket(t, asg_map)
        admin_name = admin.full_name if admin else "Unassigned"
        admin_phone = f"+{admin.phone}" if admin else "-"

        if admin_name not in admin_stats:
            admin_stats[admin_name] = {"phone": admin_phone, "assigned": 0, "resolved": 0, "pending": 0}
        
        admin_stats[admin_name]["assigned"] += 1
        if t.status_id in (3, 4):
            admin_stats[admin_name]["resolved"] += 1
        else:
            admin_stats[admin_name]["pending"] += 1

    admin_perf_data = [
        [
            Paragraph("Support Admin Name", table_header_style),
            Paragraph("Contact Phone", table_header_style),
            Paragraph("Assigned Today", table_header_style),
            Paragraph("Resolved / Closed", table_header_style),
            Paragraph("Pending", table_header_style),
        ]
    ]

    for name, stats in admin_stats.items():
        admin_perf_data.append([
            Paragraph(f"<b>{name}</b>", table_body_style),
            Paragraph(stats["phone"], table_body_style),
            Paragraph(str(stats["assigned"]), table_body_style),
            Paragraph(f"<font color='#15803D'><b>{stats['resolved']}</b></font>", table_body_bold),
            Paragraph(str(stats["pending"]), table_body_style),
        ])

    admin_perf_data.append([
        Paragraph("<b>TOTALS</b>", table_header_style),
        Paragraph("-", table_header_style),
        Paragraph(f"<b>{total_count}</b>", table_header_style),
        Paragraph(f"<b>{resolved_count}</b>", table_header_style),
        Paragraph(f"<b>{open_count + in_prog_count}</b>", table_header_style),
    ])

    admin_perf_table = Table(admin_perf_data, colWidths=[140, 110, 95, 100, 95])
    admin_perf_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), NAVY),
        ('BACKGROUND', (0,-1), (-1,-1), TEAL),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('PADDING', (0,0), (-1,-1), 5),
        ('ROWBACKGROUNDS', (0,1), (-1,-2), [colors.white, LIGHT_BG])
    ]))
    story.append(admin_perf_table)
    story.append(Spacer(1, 10))

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
        ]
    ]

    for t in today_tickets:
        emp_name = t.employee.full_name if t.employee else "Unknown"
        dept_name = t.employee.department.department_name if t.employee and t.employee.department else "General"
        cat_name = t.category.category_name if t.category else "N/A"
        sub_name = t.subcategory.subcategory_name if t.subcategory else "N/A"
        issue_name = t.issue_type.issue_name if t.issue_type else "Custom Issue"
        p_name = t.priority.priority_name if t.priority else "Medium"
        status_name = STATUS_NAMES.get(t.status_id, "Open")
        status_color = STATUS_COLORS.get(t.status_id, "#A16207")
        admin_obj = resolve_admin_for_ticket(t, asg_map)
        admin_name = admin_obj.full_name if admin_obj else "Unassigned"
        desc = t.description[:50] + "..." if len(t.description) > 50 else t.description

        p_color = "#C53030" if p_name.lower() in ("high", "urgent") else "#2D3748"

        ticket_log_data.append([
            Paragraph(f"<b>{t.ticket_number}</b>", table_body_bold),
            Paragraph(f"{emp_name}<br/><font color='#718096'>{dept_name}</font>", table_body_style),
            Paragraph(f"{cat_name} &#8594; {sub_name}<br/><i>{issue_name}</i>", table_body_style),
            Paragraph(f"<font color='{p_color}'><b>{p_name}</b></font>", table_body_style),
            Paragraph(f"<b>{admin_name}</b>", table_body_style),
            Paragraph(f"<font color='{status_color}'><b>{status_name}</b></font>", table_body_style),
        ])

    ticket_log_table = Table(ticket_log_data, colWidths=[90, 105, 135, 55, 85, 70])
    ticket_log_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), NAVY),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('PADDING', (0,0), (-1,-1), 5),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, LIGHT_BG])
    ]))
    story.append(ticket_log_table)

    story.append(Spacer(1, 12))
    footer_p = Paragraph("<font color='#718096'><b>Executive IT Operations & Support Analytics</b> | Confidential Daily Report</font>", ParagraphStyle('FooterStyle', parent=styles['Normal'], alignment=1, fontSize=8))
    story.append(footer_p)

    doc.build(story)
    print(f"PDF Daily Report successfully generated with {len(today_tickets)} live tickets: {filename}")

if __name__ == "__main__":
    create_daily_report_pdf()
