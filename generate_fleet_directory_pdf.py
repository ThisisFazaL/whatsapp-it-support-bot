import os
import sys
import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

def generate_pdf(output_filename: str = "Tagoneswa_Fleet_and_Sales_Directory_2026.pdf") -> str:
    doc = SimpleDocTemplate(
        output_filename,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    story = []
    styles = getSampleStyleSheet()

    # Color Palette
    c_primary = colors.HexColor("#0D47A1")      # Deep Corporate Blue
    c_secondary = colors.HexColor("#1976D2")    # Primary Accent
    c_header_bg = colors.HexColor("#1565C0")    # Table Header Dark Blue
    c_header_sub = colors.HexColor("#283593")   # Subheader Indigo
    c_alt_row = colors.HexColor("#F8FAFC")      # Slate 50
    c_border = colors.HexColor("#CBD5E1")       # Slate 300
    c_text_dark = colors.HexColor("#0F172A")    # Slate 900
    c_text_muted = colors.HexColor("#475569")   # Slate 600
    c_badge_green = colors.HexColor("#065F46")  # Emerald 800

    # Custom Typography
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=c_primary,
        spaceAfter=3
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#64748B"),
        spaceAfter=12
    )

    h1_style = ParagraphStyle(
        'SectionH1',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=c_secondary,
        spaceBefore=10,
        spaceAfter=4
    )

    desc_style = ParagraphStyle(
        'SectionDesc',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=8.5,
        leading=12,
        textColor=c_text_muted,
        spaceAfter=6
    )

    th_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=colors.white
    )

    tb_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=c_text_dark
    )

    tb_bold = ParagraphStyle(
        'TableCellBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=11,
        textColor=c_text_dark
    )

    tb_phone = ParagraphStyle(
        'TableCellPhone',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=11,
        textColor=c_secondary
    )

    tb_status = ParagraphStyle(
        'TableCellStatus',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=10,
        textColor=c_badge_green
    )

    # 1. Header Banner
    story.append(Paragraph("TAGONESWA HOLDINGS | LOGISTICS & FLEET", title_style))
    story.append(Paragraph(
        "WhatsApp Automation System: Operational Personnel, Roles & Contact Registry &bull; September 2026",
        subtitle_style
    ))
    story.append(HRFlowable(width="100%", thickness=2, color=c_primary, spaceBefore=0, spaceAfter=10))

    # 2. Executive Management & Operational Roles Table
    story.append(Paragraph("1. Executive Management & Key Operations Contacts", h1_style))
    story.append(Paragraph(
        "Key stakeholders authorized for Stage 3 vehicle allocation, Stage 4 allowance approvals, and Stage 7 final trip closure.",
        desc_style
    ))

    exec_headers = [
        Paragraph("Operational Role", th_style),
        Paragraph("Assigned Personnel", th_style),
        Paragraph("WhatsApp Contact", th_style),
        Paragraph("Workflow Responsibilities", th_style)
    ]

    exec_rows = [
        exec_headers,
        [
            Paragraph("Logistics Manager", tb_bold),
            Paragraph("Zayn", tb_style),
            Paragraph("+263 71 386 6223", tb_phone),
            Paragraph("Approves Driver Travel Allowances (Stage 4) & Authorizes Final Trip Closure / Discrepancy Adjudications (Stage 7)", tb_style)
        ],
        [
            Paragraph("Logistics Supervisor", tb_bold),
            Paragraph("Edward Chemhere", tb_style),
            Paragraph("+263 71 502 5982", tb_phone),
            Paragraph("Dispatches pending trip queue, allocates Truck Plates & Drivers (Stage 3)", tb_style)
        ],
        [
            Paragraph("Fleet Admin (Only)", tb_bold),
            Paragraph("Sujit Patel", tb_style),
            Paragraph("+263 71 835 2518", tb_phone),
            Paragraph("Fleet Admin Only: Receives real-time sales fleet activity notifications & executive audit closure copies", tb_style)
        ],
        [
            Paragraph("Systems Administrator", tb_bold),
            Paragraph("Fazal Saiyed", tb_style),
            Paragraph("+91 92653 68695", tb_phone),
            Paragraph("Master Admin portal, Meta Cloud API integrations, audit logging & technical escalations", tb_style)
        ]
    ]

    t_exec = Table(exec_rows, colWidths=[110, 105, 105, 220])
    t_exec.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_header_bg),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, c_alt_row]),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
    ]))
    story.append(t_exec)
    story.append(Spacer(1, 10))

    # 3. Accounts & Sales Administration Table (Sujit completely excluded from Accounts and Sales Admin)
    story.append(Paragraph("2. Accounts Team & Sales Administration", h1_style))
    story.append(Paragraph(
        "Accounts handles cash allowance release; dedicated Sales Admins conduct physical cash balancing with drivers upon return (Stage 6).",
        desc_style
    ))

    adm_headers = [
        Paragraph("Department / Branch", th_style),
        Paragraph("Designated Personnel", th_style),
        Paragraph("WhatsApp Contact", th_style),
        Paragraph("System Action & Routing", th_style)
    ]

    adm_rows = [
        adm_headers,
        [
            Paragraph("Accounts (Allowance Release)", tb_bold),
            Paragraph("Vigilance Bangezhano / Accounts", tb_style),
            Paragraph("+263 78 010 0288", tb_phone),
            Paragraph("Notified immediately upon Zayn's approval to release driver travel cash (Stage 4)", tb_style)
        ],
        [
            Paragraph("Tagoneswa Hardware (TG)", tb_bold),
            Paragraph("Everjoy Tias", tb_style),
            Paragraph("+263 78 021 6289", tb_phone),
            Paragraph("Sales Admin: Conducts physical balancing session; verifies driver delivery cash & fuel video on phone (Stage 6)", tb_style)
        ],
        [
            Paragraph("LG Plast (LG)", tb_bold),
            Paragraph("Onelly Madziro", tb_style),
            Paragraph("+263 78 738 1215", tb_phone),
            Paragraph("Sales Admin: Conducts physical balancing session for LG Plast customer deliveries (Stage 6)", tb_style)
        ],
        [
            Paragraph("Kreckle", tb_bold),
            Paragraph("Christine Chiweshe", tb_style),
            Paragraph("+263 78 349 8457", tb_phone),
            Paragraph("Sales Admin: Conducts physical balancing session for Kreckle customer deliveries (Stage 6)", tb_style)
        ],
        [
            Paragraph("Alternate / Support Sales Admin", tb_bold),
            Paragraph("Mazviita Sibongile Ruzvidzo", tb_style),
            Paragraph("+263 78 667 3351", tb_phone),
            Paragraph("Registered Sales Admin in employee directory available for balancing sessions", tb_style)
        ]
    ]

    t_adm = Table(adm_rows, colWidths=[125, 135, 125, 155])
    t_adm.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_header_sub),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, c_alt_row]),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
    ]))
    story.append(t_adm)
    story.append(Spacer(1, 10))

    # 4. Sales Representatives Directory (19 Reps)
    story.append(Paragraph("3. Registered Sales Representatives (19 Active Agents)", h1_style))
    story.append(Paragraph(
        "Sales reps initiate Favlogix trip approvals, configure trip return schedules, and manage pending shortfall ledgers.",
        desc_style
    ))

    sales_headers = [
        Paragraph("#", th_style),
        Paragraph("Sales Representative", th_style),
        Paragraph("WhatsApp Contact", th_style),
        Paragraph("Assigned Division", th_style),
        Paragraph("Bot Status", th_style)
    ]

    sales_data = [
        ("Decide Munengwa", "+263 71 953 2552", "TG Sales"),
        ("Tafadzwa Sungiso", "+263 71 790 5914", "TG Sales & Marketing"),
        ("Tanaka Mupfumi", "+263 78 043 5477", "TG Sales & Marketing"),
        ("Mercy Mungoriwo", "+263 78 048 0274", "LG Sales"),
        ("Primrose Makumbe", "+263 78 789 1815", "LG Sales"),
        ("Rudo Chikarakara", "+263 78 831 1514", "LG Sales"),
        ("Tatenda Mombechena", "+263 78 744 8975", "Lightgroove Sales & Marketing"),
        ("Ashraf Nedziwe", "+263 77 921 4825", "Sales & Marketing"),
        ("Rosa Ndimande Samihembo", "+263 78 057 3092", "Sales & Marketing"),
        ("Ruvimbo Rumhungwe", "+263 78 807 1001", "Sales & Marketing"),
        ("Talent Ruziwe", "+263 71 790 5915", "Sales & Marketing"),
        ("Vanessa Chido Zimbiti", "+263 78 272 3251", "Sales & Marketing"),
        ("Chaleka Stuart", "+263 77 550 2914", "Sales"),
        ("David Mungadzi", "+263 78 054 3771", "Sales"),
        ("Imraan Jooma", "+263 78 120 7175", "Sales"),
        ("Patience Ndlovu", "+263 78 080 6954", "Sales"),
        ("Sajjad Kazi", "+263 78 850 0565", "Sales"),
        ("Sharon Mushawa", "+263 71 249 8581", "Sales"),
        ("Wallace Muzarurwi", "+263 78 603 2376", "Sales"),
    ]

    sales_table_rows = [sales_headers]
    for idx, (name, phone, div) in enumerate(sales_data, start=1):
        sales_table_rows.append([
            Paragraph(str(idx), tb_style),
            Paragraph(name, tb_bold),
            Paragraph(phone, tb_phone),
            Paragraph(div, tb_style),
            Paragraph("ACTIVE", tb_status)
        ])

    t_sales = Table(sales_table_rows, colWidths=[24, 150, 120, 166, 80])
    t_sales.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_header_bg),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (-1, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, c_alt_row]),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
    ]))
    story.append(t_sales)
    story.append(Spacer(1, 10))

    # 5. Fleet Drivers Directory (20 Drivers)
    story.append(Paragraph("4. Registered Fleet Drivers (20 Personnel)", h1_style))
    story.append(Paragraph(
        "Auto-linked by Edward's Stage 3 dispatch. Drivers receive allowance collection alerts, odometer prompts, and transit menus.",
        desc_style
    ))

    driver_headers = [
        Paragraph("#", th_style),
        Paragraph("Driver Full Name", th_style),
        Paragraph("WhatsApp Contact", th_style),
        Paragraph("Fleet Role", th_style),
        Paragraph("Auto-Dispatch", th_style)
    ]

    drivers_data = [
        ("Ashley Zirota", "+263 78 776 0064"),
        ("Fortune Samukange", "+263 77 518 9811"),
        ("Garikai Madubeko", "+263 77 766 9972"),
        ("Godknows Kadungure", "+263 77 267 8948"),
        ("Kelvin Chitsamba", "+263 77 984 1935"),
        ("Langton Mariga", "+263 77 961 8688"),
        ("Last Kanyandura", "+263 77 573 8870"),
        ("Lastern Sabola", "+263 73 349 3338"),
        ("Michael Kamudyariwa", "+263 77 484 2059"),
        ("Nyasha Isaiah", "+263 77 772 4900"),
        ("Owen Sibanda", "+263 78 317 5517"),
        ("Peter Ncube", "+263 77 436 4811"),
        ("Praymore Madondo", "+263 78 160 3472"),
        ("Shepherd Matowanyika", "+263 77 609 3473"),
        ("Takudzwa Bafana", "+263 77 531 6554"),
        ("Tatenda Bhunu", "+263 77 134 5594"),
        ("Terrence Mupfumi", "+263 78 811 2771"),
        ("Thabani Chinamora", "+263 77 296 1453"),
        ("Tonderai Matongo", "+263 77 775 8430"),
        ("Wilbert Makoma", "+263 77 595 9241"),
    ]

    driver_table_rows = [driver_headers]
    for idx, (name, phone) in enumerate(drivers_data, start=1):
        driver_table_rows.append([
            Paragraph(str(idx), tb_style),
            Paragraph(name, tb_bold),
            Paragraph(phone, tb_phone),
            Paragraph("Commercial Driver", tb_style),
            Paragraph("VERIFIED", tb_status)
        ])

    t_driver = Table(driver_table_rows, colWidths=[24, 160, 130, 146, 80])
    t_driver.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_header_sub),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (-1, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, c_alt_row]),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
    ]))
    story.append(t_driver)
    story.append(Spacer(1, 10))

    # 6. Workflow Summary Card
    story.append(Paragraph("5. End-to-End 7-Stage Workflow Reference", h1_style))
    flow_headers = [
        Paragraph("Stage", th_style),
        Paragraph("Primary Actor", th_style),
        Paragraph("Chatbot Action & Role Security", th_style)
    ]
    flow_rows = [
        flow_headers,
        [
            Paragraph("Stage 1 & 2", tb_bold),
            Paragraph("Sales Rep", tb_style),
            Paragraph("Validates Trip in Favlogix ERP. Required minimum threshold and 4% formula strictly hidden from sales rep.", tb_style)
        ],
        [
            Paragraph("Stage 3", tb_bold),
            Paragraph("Edward (Supervisor)", tb_style),
            Paragraph("Presents FIFO trip queue. Edward inputs truck registration and driver name (auto-resolved from registry).", tb_style)
        ],
        [
            Paragraph("Stage 4", tb_bold),
            Paragraph("Sales Rep & Zayn", tb_style),
            Paragraph("Sales rep inputs return schedule; bot calculates allowances; Zayn approves; Accounts releases cash to driver.", tb_style)
        ],
        [
            Paragraph("Stage 5", tb_bold),
            Paragraph("Driver in Transit", tb_style),
            Paragraph("Driver submits departure odometer photo/digits. Transit menu provides Emergency Fuel and Returning triggers.", tb_style)
        ],
        [
            Paragraph("Stage 6", tb_bold),
            Paragraph("Sales Admin", tb_style),
            Paragraph("Sales Admin conducts physical cash balancing; inspects driver's phone video of fuel meter if emergency diesel logged.", tb_style)
        ],
        [
            Paragraph("Stage 7", tb_bold),
            Paragraph("Zayn (Logistics Mgr)", tb_style),
            Paragraph("Adjudicates variances and executes trip closure. Operational broadcast conceals all financial figures. Sujit (Fleet Admin) receives executive audit.", tb_style)
        ],
    ]
    t_flow = Table(flow_rows, colWidths=[70, 130, 340])
    t_flow.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_header_bg),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, c_alt_row]),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
    ]))
    story.append(t_flow)

    doc.build(story)
    return output_filename

if __name__ == "__main__":
    out_file = generate_pdf()
    print(f"Generated PDF successfully: {out_file}")
