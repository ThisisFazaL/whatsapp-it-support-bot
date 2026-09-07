# -*- coding: utf-8 -*-
import os
import sys
import datetime
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
    """Two-pass canvas to dynamically compute and render total page numbers and running headers."""
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
        
        # Top running header on pages > 1
        if self._pageNumber > 1:
            self.drawString(54, 11 * 72 - 36, "TAGONESWA HOLDINGS — LOGISTICS & FLEET WORKSHOP OPERATIONAL GUIDE")
            self.setFont("Helvetica", 8)
            self.drawRightString(8.5 * 72 - 54, 11 * 72 - 36, "WHATSAPP BOT & DASHBOARD SYSTEM")
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.5)
            self.line(54, 11 * 72 - 42, 8.5 * 72 - 54, 11 * 72 - 42)
        
        # Bottom running footer
        footer_text = f"Page {self._pageNumber} of {page_count}"
        self.setFont("Helvetica-Bold", 8)
        self.drawRightString(8.5 * 72 - 54, 34, footer_text)
        self.setFont("Helvetica", 8)
        self.drawString(54, 34, "CONFIDENTIAL — TAGONESWA LOGISTICS & WORKSHOP OPERATIONAL MANUAL • VERSION 2.0")
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(54, 46, 8.5 * 72 - 54, 46)
        self.restoreState()

def create_logistics_guide_pdf(filename="Tagoneswa_Logistics_Fleet_Operations_Guide.pdf"):
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()

    # Typography & Hierarchy Styles
    doc_title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#0F172A'),
        alignment=TA_LEFT,
        spaceAfter=3
    )

    doc_subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13.5,
        textColor=colors.HexColor('#2563EB'),
        alignment=TA_LEFT,
        spaceAfter=7
    )

    h1_style = ParagraphStyle(
        'SectionH1',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=15,
        textColor=colors.HexColor('#0F172A'),
        spaceBefore=10,
        spaceAfter=5,
        keepWithNext=True
    )

    h2_style = ParagraphStyle(
        'SectionH2',
        parent=styles['Heading3'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=12.5,
        textColor=colors.HexColor('#1E3A8A'),
        spaceBefore=7,
        spaceAfter=3,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        'BodyDark',
        parent=styles['BodyText'],
        fontName='Helvetica',
        fontSize=8.2,
        leading=11.8,
        textColor=colors.HexColor('#334155'),
        alignment=TA_LEFT,
        spaceAfter=3
    )

    bullet_style = ParagraphStyle(
        'BulletDark',
        parent=body_style,
        leftIndent=10,
        bulletIndent=3,
        spaceAfter=2.5
    )

    callout_style = ParagraphStyle(
        'CalloutText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.2,
        leading=11.5,
        textColor=colors.HexColor('#0F172A'),
        alignment=TA_LEFT
    )

    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.8,
        leading=9.8,
        textColor=colors.white,
        alignment=TA_LEFT
    )

    table_cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.8,
        leading=10.2,
        textColor=colors.HexColor('#1E293B'),
        alignment=TA_LEFT
    )

    table_cell_bold = ParagraphStyle(
        'TableCellBold',
        parent=table_cell_style,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#0F172A')
    )

    msg_bubble_style = ParagraphStyle(
        'MsgBubble',
        parent=styles['Normal'],
        fontName='Courier-Bold',
        fontSize=7.8,
        leading=10.5,
        textColor=colors.HexColor('#0F172A'),
        alignment=TA_LEFT
    )

    story = []

    # =========================================================================
    # COVER / HEADER BANNER
    # =========================================================================
    banner_data = [
        [
            Paragraph("🚚 TAGONESWA HOLDINGS • LOGISTICS & FLEET MANAGEMENT", ParagraphStyle('B1', fontName='Helvetica-Bold', fontSize=8.5, textColor=colors.HexColor('#2563EB'))),
            Paragraph(f"DATE: {datetime.datetime.now().strftime('%d %B %Y')} | REF: SOP-FLT-2026", ParagraphStyle('B2', fontName='Helvetica', fontSize=8, textColor=colors.HexColor('#64748B'), alignment=TA_RIGHT))
        ]
    ]
    t_banner = Table(banner_data, colWidths=[3.8 * inch, 3.2 * inch])
    t_banner.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(t_banner)
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#E2E8F0'), spaceAfter=6))

    story.append(Paragraph("Logistics & Fleet Operations Guide", doc_title_style))
    story.append(Paragraph("Standard Operating Procedures for Drivers, Supervisors, Mechanics, Purchasing & Management", doc_subtitle_style))
    story.append(Spacer(1, 3))

    # Executive Overview Box
    exec_summary = (
        "<b>System Purpose:</b> This guide explains the automated fleet ticketing and workshop maintenance workflow "
        "powered by the <b>Tagoneswa WhatsApp Bot</b> and the <b>Live Operations Dashboard</b>. Every truck defect, gatekeeper triage, "
        "spare parts procurement, and road-test quality inspection is digitally tracked with real-time timestamps, accountability, and zero paperwork."
    )
    t_exec = Table([[Paragraph(exec_summary, callout_style)]], colWidths=[7.0 * inch])
    t_exec.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#EFF6FF')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#BFDBFE')),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(t_exec)
    story.append(Spacer(1, 8))

    # =========================================================================
    # SECTION 1: ROLE & WORKFLOW ARCHITECTURE MATRIX
    # =========================================================================
    story.append(Paragraph("1. Role Overview & System Responsibilities", h1_style))
    story.append(Paragraph(
        "The logistics ecosystem assigns specific permissions and automated WhatsApp menus based on each staff member's registered role:",
        body_style
    ))

    role_matrix_data = [
        [
            Paragraph("Role", table_header_style),
            Paragraph("Primary Responsibility", table_header_style),
            Paragraph("WhatsApp Workflow", table_header_style),
            Paragraph("Key Output / Action", table_header_style),
        ],
        [
            Paragraph("<b>Driver / Clerk</b><br/><font color='#64748B'>CLERK / DRIVER</font>", table_cell_style),
            Paragraph("Report vehicle breakdown or defect from the field/yard.", table_cell_style),
            Paragraph("Search truck by plate/number, select fault category, enter notes &amp; photo.", table_cell_style),
            Paragraph("Generates Ticket ID<br/>(<code>TKT-FLT-XXXXX</code>)", table_cell_bold),
        ],
        [
            Paragraph("<b>Supervisor</b><br/><font color='#64748B'>GATEKEEPER</font>", table_cell_style),
            Paragraph("Triage faults, assign mechanics &amp; conduct final QC road-tests.", table_cell_style),
            Paragraph("Receives instant triage alerts with buttons: [Handle Internally] vs [Send to Workshop].", table_cell_style),
            Paragraph("Approves repairs &amp; Signs off QC Road-Test", table_cell_bold),
        ],
        [
            Paragraph("<b>Mechanic</b><br/><font color='#64748B'>TECHNICIAN</font>", table_cell_style),
            Paragraph("Execute mechanical repairs, request spares &amp; log costing.", table_cell_style),
            Paragraph("Enters repair ETA, requests spare parts with photo, marks repair done with cost.", table_cell_style),
            Paragraph("SLA Compliance &amp; Repair Notes", table_cell_bold),
        ],
        [
            Paragraph("<b>Purchasing</b><br/><font color='#64748B'>PROCUREMENT</font>", table_cell_style),
            Paragraph("Source, clarify, purchase &amp; issue requested spare parts.", table_cell_style),
            Paragraph("Receives parts alerts with mechanic photos. Can request clarification or confirm issue.", table_cell_style),
            Paragraph("Parts Sourced &amp; Issued to Floor", table_cell_bold),
        ],
        [
            Paragraph("<b>Management</b><br/><font color='#64748B'>CONTROLLER</font>", table_cell_style),
            Paragraph("Live fleet visibility, KPI oversight &amp; cost governance.", table_cell_style),
            Paragraph("Accesses Live Web Portal (<code>/dashboard#logistics</code>) with real-time filters.", table_cell_style),
            Paragraph("Executive Audit &amp; Fleet Uptime", table_cell_bold),
        ],
    ]

    t_roles = Table(role_matrix_data, colWidths=[1.3 * inch, 1.9 * inch, 2.3 * inch, 1.5 * inch])
    t_roles.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1E3A8A')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ('TOPPADDING', (0,0), (-1,-1), 3.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3.5),
        ('LEFTPADDING', (0,0), (-1,-1), 5),
        ('RIGHTPADDING', (0,0), (-1,-1), 5),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#FFFFFF'), colors.HexColor('#F8FAFC')]),
    ]))
    story.append(t_roles)
    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 2: END-TO-END LIFECYCLE (THE 6 STAGES)
    # =========================================================================
    story.append(Paragraph("2. The 6-Stage Fleet Maintenance Lifecycle", h1_style))
    story.append(Paragraph(
        "Every truck defect transitions through 6 structured lifecycle milestones ensuring full visibility across all departments:",
        body_style
    ))

    stages_data = [
        [
            Paragraph("Stage", table_header_style),
            Paragraph("Status Tag", table_header_style),
            Paragraph("Active Dept", table_header_style),
            Paragraph("What Happens at This Stage", table_header_style),
        ],
        [
            Paragraph("<b>1. Defect Logging</b>", table_cell_style),
            Paragraph("<font color='#D97706'><b>UNDER_REVIEW</b></font>", table_cell_style),
            Paragraph("Driver / Clerk", table_cell_style),
            Paragraph("Driver selects truck plate, selects component failure, adds description and attaches photo.", table_cell_style),
        ],
        [
            Paragraph("<b>2. Gatekeeper Triage</b>", table_cell_style),
            Paragraph("<font color='#2563EB'><b>WITH_MECHANIC</b></font>", table_cell_style),
            Paragraph("Supervisor", table_cell_style),
            Paragraph("Supervisor evaluates severity: routes minor faults internally or assigns mechanic for workshop repair.", table_cell_style),
        ],
        [
            Paragraph("<b>3. Mechanic Assessment</b>", table_cell_style),
            Paragraph("<font color='#4F46E5'><b>IN_PROGRESS</b></font>", table_cell_style),
            Paragraph("Mechanic", table_cell_style),
            Paragraph("Assigned mechanic inspects truck, commits repair ETA (e.g. 'Today 4 PM'), and begins floor wrenching.", table_cell_style),
        ],
        [
            Paragraph("<b>4. Spares Requisition</b>", table_cell_style),
            Paragraph("<font color='#DC2626'><b>AWAITING_PARTS</b></font>", table_cell_style),
            Paragraph("Purchasing / Stores", table_cell_style),
            Paragraph("If spares needed, mechanic requests parts with sample photo. Purchasing clarifies specs &amp; issues parts.", table_cell_style),
        ],
        [
            Paragraph("<b>5. Quality Control (QC)</b>", table_cell_style),
            Paragraph("<font color='#059669'><b>AWAITING_TEST</b></font>", table_cell_style),
            Paragraph("Supervisor", table_cell_style),
            Paragraph("Mechanic submits work notes, parts used &amp; costing. System notifies Supervisor to perform road-test QC.", table_cell_style),
        ],
        [
            Paragraph("<b>6. Return to Fleet</b>", table_cell_style),
            Paragraph("<font color='#475569'><b>CLOSED</b></font>", table_cell_style),
            Paragraph("Active Fleet", table_cell_style),
            Paragraph("Vehicle passes inspection, ticket is closed, SLA metrics recorded, and truck is cleared for commercial loading.", table_cell_style),
        ],
    ]

    t_stages = Table(stages_data, colWidths=[1.3 * inch, 1.4 * inch, 1.3 * inch, 3.0 * inch])
    t_stages.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0F172A')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ('TOPPADDING', (0,0), (-1,-1), 3.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3.5),
        ('LEFTPADDING', (0,0), (-1,-1), 5),
        ('RIGHTPADDING', (0,0), (-1,-1), 5),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#FFFFFF'), colors.HexColor('#F8FAFC')]),
    ]))
    story.append(t_stages)

    story.append(PageBreak())

    # =========================================================================
    # SECTION 3: ROLE-BY-ROLE STEP-BY-STEP OPERATIONAL GUIDE
    # =========================================================================
    story.append(Paragraph("3. Detailed Step-by-Step Guide by Role", h1_style))
    story.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor('#CBD5E1'), spaceAfter=8))

    # --- ROLE 1: DRIVER / CLERK ---
    story.append(Paragraph("ROLE 1: Drivers &amp; Logistics Clerks (Reporting Defects)", h2_style))
    story.append(Paragraph(
        "Drivers and logistics assistants use WhatsApp to log truck defects in under 60 seconds with simple interactive prompts:",
        body_style
    ))

    driver_steps = [
        "<b>Step 1: Start Chat</b> — Send <code>Hi</code>, <code>Truck</code>, or <code>Menu</code> to the Tagoneswa Bot on WhatsApp.",
        "<b>Step 2: Enter Truck Number</b> — Type the plate number or truck digit (e.g. for plate <code>AGZ 7331</code>, simply type <code>7331</code>).",
        "<b>Step 3: Confirm Vehicle</b> — The bot will return the exact vehicle match (e.g. <i>'Truck #7331 - Volvo FH16 540 [AGZ 7331]'</i>). Tap <b>[✅ Yes, Confirm Truck]</b>.",
        "<b>Step 4: Select Defect Category</b> — Choose from 7 standardized vehicle assemblies: "
        "<i>1. Engine &amp; Powertrain, 2. Brakes &amp; Air System, 3. Electrical &amp; Lighting, 4. Suspension &amp; Tyres, 5. Transmission &amp; Drivetrain, 6. Body &amp; Cabin, 7. Cooling &amp; Fuel</i>.",
        "<b>Step 5: Select Subcategory Fault</b> — Choose the specific defect (e.g. <i>Low Air Pressure, Oil Leak, Turbo Loss, Clutch Slipping</i>).",
        "<b>Step 6: Describe Issue &amp; Attach Photo</b> — Type details of the fault (e.g. <i>'Air pressure drops below 6 bar when braking on hill'</i>). Upload a photo of the damaged part or tap <b>[⏭️ Skip Photo]</b>.",
        "<b>Step 7: Ticket Received</b> — The bot immediately generates a unique Ticket ID (e.g. <code>TKT-FLT-20260907-00004</code>) and alerts the Logistics Supervisor."
    ]
    for stp in driver_steps:
        story.append(Paragraph(f"• {stp}", bullet_style))
    story.append(Spacer(1, 4))

    # Driver Example Message Box
    driver_box = (
        "<b>📱 Sample WhatsApp Driver Confirmation:</b><br/>"
        "<code>🎫 TICKET LOGGED: TKT-FLT-20260907-00004<br/>"
        "🚚 Vehicle: Truck #7331 (Volvo FH16 [AGZ 7331])<br/>"
        "📌 Defect: Brakes &amp; Air System ➔ Low air pressure / compressor fault<br/>"
        "📝 Notes: 'Air tank takes 20 mins to build pressure and warning buzzer rings'<br/>"
        "⏳ Status: UNDER SUPERVISOR REVIEW</code>"
    )
    t_drv_box = Table([[Paragraph(driver_box, msg_bubble_style)]], colWidths=[7.0 * inch])
    t_drv_box.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F1F5F9')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#CBD5E1')),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 7),
        ('RIGHTPADDING', (0,0), (-1,-1), 7),
    ]))
    story.append(t_drv_box)
    story.append(Spacer(1, 8))

    # --- ROLE 2: SUPERVISOR / GATEKEEPER ---
    story.append(Paragraph("ROLE 2: Logistics Supervisors &amp; Gatekeepers (Triage &amp; Quality Control)", h2_style))
    story.append(Paragraph(
        "The Supervisor acts as the operational gatekeeper to prevent workshop bottlenecks and verify repair standards:",
        body_style
    ))

    sup_steps = [
        "<b>Gatekeeper Triage (Instant Decision):</b> When a ticket is submitted, the Supervisor receives an instant WhatsApp alert with two one-tap buttons:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;• <b>[🛠️ Handle Internally]:</b> For minor fixes (e.g. bulb swap, wiper blade, air top-up). The ticket is solved on the spot without taking bay space.<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;• <b>[🏭 Send to Workshop]:</b> For mechanical issues requiring tooling, spares, or bay inspection.",
        "<b>Mechanic Assignment:</b> If routed to the workshop, the Supervisor selects an active mechanic from the roster (e.g. <i>Sajid, Farai, Simba</i>).",
        "<b>Live Floor Supervision:</b> The Supervisor monitors job progress, spares requisitions, and supplier delays from WhatsApp or the Live Dashboard.",
        "<b>QC Road-Test Inspection:</b> When the mechanic marks work done, the Supervisor receives the QC testing notification:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;• <b>[✅ Passed QC Test]:</b> Vehicle passes safety/road test. Status changes to <b>CLOSED</b> and vehicle returns to active fleet.<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;• <b>[⚠️ Failed / Rework]:</b> Supervisor enters defect notes; truck returns to mechanic with urgent rework priority."
    ]
    for stp in sup_steps:
        story.append(Paragraph(f"• {stp}", bullet_style))
    story.append(Spacer(1, 8))

    # --- ROLE 3: WORKSHOP MECHANIC ---
    story.append(Paragraph("ROLE 3: Workshop Mechanics &amp; Technicians (Repairs &amp; Spares)", h2_style))
    story.append(Paragraph(
        "Mechanics receive assigned work orders on WhatsApp, commit completion times, order spare parts, and record job costing:",
        body_style
    ))

    mech_steps = [
        "<b>Job Alert &amp; ETA Commitment:</b> Mechanic receives assignment with truck details, fault notes, and photo. Mechanic replies with expected completion time (e.g. <i>'Today 3 PM'</i> or <i>'Tomorrow 10 AM'</i>).",
        "<b>Ordering Spare Parts:</b> If parts are required, mechanic taps <b>[📦 Request Parts]</b> &rarr; enters part description (e.g. <i>'Brake booster diaphragm &amp; air valve'</i>) &rarr; snaps and uploads photo of the worn component.",
        "<b>Purchasing Inquiries:</b> If Purchasing asks for clarification, mechanic replies directly on WhatsApp with dimensions or OEM numbers.",
        "<b>Marking Work Completed:</b> When mechanical repairs are done, mechanic taps <b>[✅ Mark Work Done]</b> &rarr; enters resolution notes &rarr; enters parts cost (e.g. <code>$140</code>) &rarr; enters labor hours &rarr; submits for Supervisor QC inspection.",
        "<b>SLA Benchmark:</b> System automatically compares completion timestamp against committed ETA to calculate on-time SLA performance."
    ]
    for stp in mech_steps:
        story.append(Paragraph(f"• {stp}", bullet_style))

    story.append(PageBreak())

    # --- ROLE 4: PURCHASING & PROCUREMENT ---
    story.append(Paragraph("ROLE 4: Purchasing &amp; Procurement Officers (Spare Parts)", h2_style))
    story.append(Paragraph(
        "The Purchasing department manages spare parts procurement seamlessly with zero paper requisitions:",
        body_style
    ))

    purch_steps = [
        "<b>Instant Requisition Alert:</b> Purchasing receives instant alert with Ticket ID, Truck Number, Part Name, and mechanic's attached sample photo.",
        "<b>Requesting Clarification:</b> If part specifications or model details are needed, Purchasing taps <b>[❓ Request Clarification]</b> and types the question (e.g. <i>'Is this 24mm or 28mm thread?'</i>). Bot forwards question to mechanic.",
        "<b>Issuing Parts:</b> Once spare parts arrive from suppliers or are issued from inventory, Purchasing taps <b>[✅ Parts Received &amp; Issued]</b>. The mechanic is instantly alerted that parts are ready for installation."
    ]
    for stp in purch_steps:
        story.append(Paragraph(f"• {stp}", bullet_style))
    story.append(Spacer(1, 8))

    # --- ROLE 5: MANAGEMENT & CONTROLLER ---
    story.append(Paragraph("ROLE 5: Management &amp; Logistics Controllers (Live Web Portal)", h2_style))
    story.append(Paragraph(
        "Logistics managers and directors monitor the entire fleet operations in real time via the secure web console at <b><code>/dashboard#logistics</code></b>:",
        body_style
    ))

    mgmt_points = [
        "<b>Real-Time KPI Metric Cards:</b> Instant counts of Total Registered Fleet (39 Trucks), Supervisor Under Review, Active in Workshop, Awaiting Spares, and QC Road-Test.",
        "<b>Descending Ticket View:</b> Live table always displays the newest logged tickets at the top with color-coded status badges.",
        "<b>Interactive Filtering:</b> Filter vehicles by assigned mechanic, workshop stage, truck number, plate number, or fault category.",
        "<b>Cost &amp; SLA Tracking:</b> View parts costing, labor expenses, mechanic turnaround speed, and QC pass/fail ratios across the entire fleet.",
        "<b>Mobile-Optimized Interface:</b> Fully responsive design with touch swiping and quick-refresh button for warehouse floor tablets and smartphones."
    ]
    for pt in mgmt_points:
        story.append(Paragraph(f"• {pt}", bullet_style))
    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 4: FAULT CATEGORIES & COMPONENT REFERENCE
    # =========================================================================
    story.append(Paragraph("4. Standard Fault Classification Reference", h1_style))
    story.append(Paragraph(
        "To ensure precise diagnostic reporting, all faults are categorized under the following standard fleet assemblies:",
        body_style
    ))

    cat_data = [
        [
            Paragraph("Assembly Category", table_header_style),
            Paragraph("Standard Subcategories / Fault Examples", table_header_style),
        ],
        [
            Paragraph("<b>1. Engine &amp; Powertrain</b>", table_cell_bold),
            Paragraph("Engine overheating, Turbo boost loss, Oil pressure drop, Oil leak, Abnormal knocking/vibration, Injector failure.", table_cell_style),
        ],
        [
            Paragraph("<b>2. Brakes &amp; Air System</b>", table_cell_bold),
            Paragraph("Low air pressure, Air governor/leak, Brake drum/linings worn, ABS warning lamp, Foot valve air dump, Air dryer purge.", table_cell_style),
        ],
        [
            Paragraph("<b>3. Electrical &amp; Lighting</b>", table_cell_bold),
            Paragraph("Alternator charge failure, Starter motor dead, Battery dead/terminals, Headlights/Indicators, Fuse box short circuit, Wiring harness.", table_cell_style),
        ],
        [
            Paragraph("<b>4. Suspension &amp; Tyres</b>", table_cell_bold),
            Paragraph("Air suspension bellow leak, Leaf spring cracked/broken, Tyre puncture/blowout, Wheel bearing play, Kingpin wear, Alignment.", table_cell_style),
        ],
        [
            Paragraph("<b>5. Transmission &amp; Drivetrain</b>", table_cell_bold),
            Paragraph("Clutch slipping/hard pedal, Gearbox gear selection grind, Propshaft center bearing play, Differential oil leak, Universal joint.", table_cell_style),
        ],
        [
            Paragraph("<b>6. Body, Cabin &amp; Chassis</b>", table_cell_bold),
            Paragraph("Windscreen cracked, Door latch/mirror damaged, Fifth wheel coupling slack, Mudguard loose, Cabin tilt pump, Chassis crack.", table_cell_style),
        ],
        [
            Paragraph("<b>7. Cooling &amp; Fuel System</b>", table_cell_bold),
            Paragraph("Radiator water leak, Water pump squeal, Diesel fuel leak, Primary/Secondary fuel filter clogged, Fuel tank strap loose.", table_cell_style),
        ],
    ]

    t_cat = Table(cat_data, colWidths=[2.2 * inch, 4.8 * inch])
    t_cat.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1E3A8A')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING', (0,0), (-1,-1), 5),
        ('RIGHTPADDING', (0,0), (-1,-1), 5),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#FFFFFF'), colors.HexColor('#F8FAFC')]),
    ]))
    story.append(t_cat)
    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 5: QUICK ACTION COMMANDS & BEST PRACTICES
    # =========================================================================
    story.append(Paragraph("5. WhatsApp Quick Commands &amp; Best Practices", h1_style))
    
    cmd_data = [
        [
            Paragraph("Keyword / Action", table_header_style),
            Paragraph("Permitted Roles", table_header_style),
            Paragraph("System Action / Behavior", table_header_style),
        ],
        [
            Paragraph("<code>Hi</code>, <code>Menu</code>, <code>Truck</code>", table_cell_bold),
            Paragraph("All Staff", table_cell_style),
            Paragraph("Resets active conversation and displays the role-specific operational menu.", table_cell_style),
        ],
        [
            Paragraph("<code>Status</code>", table_cell_bold),
            Paragraph("Supervisor, Mechanic", table_cell_style),
            Paragraph("Displays active workshop job queue, pending parts requisitions, and open tickets.", table_cell_style),
        ],
        [
            Paragraph("<code>Reset</code>, <code>Cancel</code>", table_cell_bold),
            Paragraph("All Staff", table_cell_style),
            Paragraph("Cancels current multi-step flow (e.g. defect reporting) and returns to main menu.", table_cell_style),
        ],
    ]
    t_cmd = Table(cmd_data, colWidths=[1.8 * inch, 1.5 * inch, 3.7 * inch])
    t_cmd.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0F172A')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ('TOPPADDING', (0,0), (-1,-1), 3.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3.5),
        ('LEFTPADDING', (0,0), (-1,-1), 5),
        ('RIGHTPADDING', (0,0), (-1,-1), 5),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#FFFFFF'), colors.HexColor('#F8FAFC')]),
    ]))
    story.append(t_cmd)
    story.append(Spacer(1, 6))

    # Best practices box
    best_practice_text = (
        "<b>Operational Best Practices for Fleet Teams:</b><br/>"
        "• <b>Clear Defect Notes:</b> Drivers should include specific symptoms (e.g. speed, gear, or temperature when fault occurred).<br/>"
        "• <b>Clear Photos:</b> Take well-lit, close-up photos of leaks, cracked springs, or worn tyres to speed up supervisor approval.<br/>"
        "• <b>Timely ETA Updates:</b> Mechanics must enter realistic ETAs so logistics controllers can plan vehicle load dispatches.<br/>"
        "• <b>Mandatory QC Road-Test:</b> No truck is returned to the active fleet without a documented supervisor road-test sign-off."
    )
    t_bp = Table([[Paragraph(best_practice_text, callout_style)]], colWidths=[7.0 * inch])
    t_bp.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F0FDF4')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#86EFAC')),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(t_bp)

    # Build PDF
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"SUCCESS: Logistics Guide PDF generated successfully -> {filename}")

if __name__ == "__main__":
    out_pdf = "Tagoneswa_Logistics_Fleet_Operations_Guide.pdf"
    if len(sys.argv) > 1:
        out_pdf = sys.argv[1]
    create_logistics_guide_pdf(out_pdf)
