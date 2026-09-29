import os
import sys
import datetime
import shutil
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

def add_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont('Helvetica', 7.5)
    canvas.setFillColor(colors.HexColor('#64748B'))
    canvas.drawString(36, 20, "Tagoneswa Holdings • Logistics & Fleet WhatsApp Automation Contact Registry (Confidential)")
    canvas.drawRightString(doc.pagesize[0] - 36, 20, f"Page {doc.page} of 2")
    canvas.restoreState()

def generate_pdf(output_filename: str = "Tagoneswa_Fleet_and_Sales_Directory_2026.pdf") -> str:
    doc = SimpleDocTemplate(
        output_filename,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=32,
        bottomMargin=32
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
    c_badge_amber = colors.HexColor("#B45309")  # Amber 700

    # Custom Typography
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=c_primary,
        spaceAfter=2
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#64748B"),
        spaceAfter=8
    )

    h1_style = ParagraphStyle(
        'SectionH1',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=14,
        textColor=c_secondary,
        spaceBefore=6,
        spaceAfter=2
    )

    desc_style = ParagraphStyle(
        'SectionDesc',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=7.5,
        leading=10,
        textColor=c_text_muted,
        spaceAfter=4
    )

    th_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.white
    )

    tb_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7,
        leading=9,
        textColor=c_text_dark
    )

    tb_bold = ParagraphStyle(
        'TableCellBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7,
        leading=9,
        textColor=c_text_dark
    )

    tb_phone = ParagraphStyle(
        'TableCellPhone',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7,
        leading=9,
        textColor=c_secondary
    )

    tb_status = ParagraphStyle(
        'TableCellStatus',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=6.5,
        leading=8.5,
        textColor=c_badge_green
    )

    tb_pending = ParagraphStyle(
        'TableCellPending',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=6.5,
        leading=8.5,
        textColor=c_badge_amber
    )

    # =========================================================================
    # PAGE 1: MANAGEMENT, ACCOUNTS, SALES ADMIN & 7-STAGE WORKFLOW
    # =========================================================================

    # 1. Header Banner
    story.append(Paragraph("TAGONESWA HOLDINGS | LOGISTICS & FLEET", title_style))
    story.append(Paragraph(
        "WhatsApp Automation System: Operational Personnel, Roles & Contact Registry &bull; September 2026",
        subtitle_style
    ))
    story.append(HRFlowable(width="100%", thickness=1.5, color=c_primary, spaceBefore=0, spaceAfter=6))

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

    t_exec = Table(exec_rows, colWidths=[105, 105, 105, 225])
    t_exec.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_header_bg),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, c_alt_row]),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
    ]))
    story.append(t_exec)
    story.append(Spacer(1, 6))

    # 3. Accounts & Sales Administration Table
    story.append(Paragraph("2. Accounts Team & Sales Administration", h1_style))
    story.append(Paragraph(
        "Accounts handles cash allowance release (Stage 4); company-specific Sales Admins conduct physical cash balancing with drivers upon return (Stage 6).",
        desc_style
    ))

    adm_headers = [
        Paragraph("Department / Company", th_style),
        Paragraph("Designated Personnel", th_style),
        Paragraph("WhatsApp Contact", th_style),
        Paragraph("System Action & Routing", th_style)
    ]

    adm_rows = [
        adm_headers,
        [
            Paragraph("Accounts (Allowance Release)", tb_bold),
            Paragraph("Vigilance Bangezhano", tb_style),
            Paragraph("+263 78 010 0288", tb_phone),
            Paragraph("Notified immediately upon Zayn's approval to release driver travel cash (Stage 4)", tb_style)
        ],
        [
            Paragraph("Accounts (Allowance Release)", tb_bold),
            Paragraph("Munashe Milca", tb_style),
            Paragraph("+263 78 806 8567", tb_phone),
            Paragraph("Accounts team member authorized for cash allowance release (Stage 4)", tb_style)
        ],
        [
            Paragraph("Tagoneswa Hardware (TG)", tb_bold),
            Paragraph("Christine Chiweshe", tb_style),
            Paragraph("+263 78 349 8457", tb_phone),
            Paragraph("Sales Admin: Conducts physical balancing session; verifies driver delivery cash & fuel video on phone (Stage 6)", tb_style)
        ],
        [
            Paragraph("LG Plast (LG)", tb_bold),
            Paragraph("Onelly Madziro", tb_style),
            Paragraph("+263 78 738 1215", tb_phone),
            Paragraph("Sales Admin: Conducts physical balancing session for LG Plast customer deliveries (Stage 6)", tb_style)
        ],
        [
            Paragraph("LG Plast (LG)", tb_bold),
            Paragraph("Mazviita Sibongile Ruzvidzo", tb_style),
            Paragraph("+263 71 817 4894", tb_phone),
            Paragraph("Sales Admin: Authorized for LG Plast balancing sessions and customer reconciliation (Stage 6)", tb_style)
        ],
        [
            Paragraph("Kreckle", tb_bold),
            Paragraph("Everjoy Tias", tb_style),
            Paragraph("+263 78 021 6289", tb_phone),
            Paragraph("Sales Admin: Conducts physical balancing session for Kreckle customer deliveries (Stage 6)", tb_style)
        ]
    ]

    t_adm = Table(adm_rows, colWidths=[120, 130, 115, 175])
    t_adm.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_header_sub),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, c_alt_row]),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
    ]))
    story.append(t_adm)
    story.append(Spacer(1, 6))

    # 4. Workflow Summary Card
    story.append(Paragraph("3. End-to-End 7-Stage Workflow Reference", h1_style))
    story.append(Paragraph(
        "Structured lifecycle ensuring data confidentiality, driver accountability, and physical cash audit.",
        desc_style
    ))
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
            Paragraph("Adjudicates variances and executes trip closure. Operational broadcast conceals financial figures. Sujit (Fleet Admin) receives executive audit.", tb_style)
        ],
    ]
    t_flow = Table(flow_rows, colWidths=[70, 120, 350])
    t_flow.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_header_bg),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, c_alt_row]),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
    ]))
    story.append(t_flow)

    # PAGE BREAK TO PAGE 2
    story.append(PageBreak())

    # =========================================================================
    # PAGE 2: SALES REPRESENTATIVES & COMMERCIAL FLEET DRIVERS
    # =========================================================================
    story.append(Paragraph("4. Registered Sales Representatives by Company (18 Agents)", h1_style))
    story.append(Paragraph(
        "Sales reps initiate Favlogix trip approvals, configure return schedules, and manage delivery collections.",
        desc_style
    ))

    sales_headers = [
        Paragraph("#", th_style),
        Paragraph("Sales Representative", th_style),
        Paragraph("WhatsApp Contact", th_style),
        Paragraph("Company / Division", th_style),
        Paragraph("Bot Status", th_style)
    ]

    sales_data = [
        # LG Plast (LG)
        ("Ashraf Nedziwe", "+263 77 921 4825", "LG Plast (LG)", "ACTIVE"),
        ("Mercy Mungoriwo", "+263 71 142 1201", "LG Plast (LG)", "ACTIVE"),
        ("Callistus Keche", "+263 77 742 5204", "LG Plast (LG)", "ACTIVE"),
        ("Primrose Makumbe", "+263 78 133 7103", "LG Plast (LG)", "ACTIVE"),
        ("Sharon Mushava", "+263 71 249 8581", "LG Plast (LG)", "ACTIVE"),
        ("Tatenda Mombechena", "+263 78 744 8975", "LG Plast (LG)", "ACTIVE"),
        ("Wallace Muzarurwi", "+263 78 603 2376", "LG Plast (LG)", "ACTIVE"),
        # Tagoneswa Hardware (TG)
        ("Stuart Chaleka", "+263 71 864 3451", "Tagoneswa Hardware (TG)", "ACTIVE"),
        ("Vanessa Zimbiti", "+263 78 272 3251", "Tagoneswa Hardware (TG)", "ACTIVE"),
        ("Tafadzwa Sungiso", "+263 71 790 5914", "Tagoneswa Hardware (TG)", "ACTIVE"),
        ("Talent Ruziwe", "+263 71 790 5915", "Tagoneswa Hardware (TG)", "ACTIVE"),
        ("Tafadzwa Chikove", "+263 78 823 1069", "Tagoneswa Hardware (TG)", "ACTIVE"),
        ("Tanaka Mupfumi", "+263 78 043 5477", "Tagoneswa Hardware (TG)", "ACTIVE"),
        # Kreckle
        ("David Mungadzi", "+263 78 054 3771", "Kreckle", "ACTIVE"),
        ("Patience Ndlovu", "+263 78 080 6954", "Kreckle", "ACTIVE"),
        ("Mufaro Gambiza", "+263 78 310 3611", "Kreckle", "ACTIVE"),
        ("Kudzai Marevesa", "(Pending Contact)", "Kreckle", "PENDING_PHONE"),
        ("Ndiwande Samihembo Rosa", "+263 78 057 3092", "Kreckle", "ACTIVE"),
    ]

    sales_table_rows = [sales_headers]
    for idx, (name, phone, div, status) in enumerate(sales_data, start=1):
        status_para = Paragraph("ACTIVE", tb_status) if status == "ACTIVE" else Paragraph("PENDING", tb_pending)
        phone_para = Paragraph(phone, tb_phone) if status == "ACTIVE" else Paragraph(phone, tb_style)
        sales_table_rows.append([
            Paragraph(str(idx), tb_style),
            Paragraph(name, tb_bold),
            phone_para,
            Paragraph(div, tb_style),
            status_para
        ])

    t_sales = Table(sales_table_rows, colWidths=[28, 140, 115, 177, 80], repeatRows=1)
    t_sales.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_header_bg),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (-1, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1.8),
        ('TOPPADDING', (0, 0), (-1, -1), 1.8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, c_alt_row]),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
    ]))
    story.append(t_sales)
    story.append(Spacer(1, 6))

    # 5. Fleet Drivers Directory (21 Drivers)
    story.append(Paragraph("5. Registered Fleet & Logistics Commercial Drivers (21 Drivers)", h1_style))
    story.append(Paragraph(
        "Auto-linked by Edward's Stage 3 dispatch. Drivers receive allowance collection alerts, odometer verification prompts, and transit menus.",
        desc_style
    ))

    driver_headers = [
        Paragraph("#", th_style),
        Paragraph("Driver Full Name", th_style),
        Paragraph("WhatsApp Contact", th_style),
        Paragraph("Fleet Role", th_style),
        Paragraph("Status", th_style)
    ]

    drivers_data = [
        ("Ashley Zirota", "+263 71 771 9287"),
        ("Fortune Samukange", "+263 77 387 0555"),
        ("Garikai Madubeko", "+263 77 766 9972"),
        ("Godknows Kadungure", "+263 77 267 8948"),
        ("Kelvin Chitsamba", "+263 77 984 1935"),
        ("Langton Mariga", "+263 77 961 8688"),
        ("Last Kanyandura", "+263 77 573 8870"),
        ("Lastern Sabola", "+263 77 256 7464"),
        ("Michael Kamudyariwa", "+263 77 484 2059"),
        ("Nathan", "+263 77 224 0303"),
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

    t_driver = Table(driver_table_rows, colWidths=[28, 152, 125, 155, 80], repeatRows=1)
    t_driver.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_header_sub),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (-1, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1.8),
        ('TOPPADDING', (0, 0), (-1, -1), 1.8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, c_alt_row]),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
    ]))
    story.append(t_driver)

    doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)

    # Copy to artifacts directory
    artifact_dir = r"C:\Users\nytfa\.gemini\antigravity\brain\d9ad7a04-6df4-4d29-a271-668ed0d8f9d0"
    if os.path.exists(artifact_dir):
        dest_path = os.path.join(artifact_dir, output_filename)
        shutil.copy2(output_filename, dest_path)
        print(f"Copied PDF to artifact directory: {dest_path}")

    return output_filename

if __name__ == "__main__":
    out_file = generate_pdf()
    print(f"Generated PDF successfully: {out_file}")
