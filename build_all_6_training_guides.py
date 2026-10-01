# -*- coding: utf-8 -*-
"""
Full Generator for all 6 Sales to Fleet Training Guides
"""

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

USABLE_WIDTH = 7.5 * inch


class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, role_title="TRAINING GUIDE", **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []
        self.role_title = role_title

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
        if self._pageNumber > 1:
            self.drawString(36, 11 * 72 - 28, "TAGONESWA HOLDINGS • SALES TO FLEET TRAINING MANUAL")
            self.drawRightString(8.5 * 72 - 36, 11 * 72 - 28, self.role_title.upper())
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.5)
            self.line(36, 11 * 72 - 32, 8.5 * 72 - 36, 11 * 72 - 32)

        page_str = f"Page {self._pageNumber} of {page_count}"
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#64748B"))
        self.drawRightString(8.5 * 72 - 36, 22, page_str)
        self.setFont("Helvetica", 8)
        self.drawString(36, 22, f"CONFIDENTIAL — TAGONESWA OPERATIONAL SYSTEM • {self.role_title.upper()}")
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(36, 32, 8.5 * 72 - 36, 32)
        self.restoreState()


def get_styles():
    styles = getSampleStyleSheet()
    custom_styles = {
        'Normal': styles['Normal'],
        'DocTitle': ParagraphStyle('DocTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=16, leading=20, textColor=colors.HexColor('#0F172A'), spaceAfter=2),
        'DocSubTitle': ParagraphStyle('DocSubTitle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, leading=12, textColor=colors.HexColor('#2563EB'), spaceAfter=3),
        'SectionH1': ParagraphStyle('SectionH1', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=10.5, leading=14, textColor=colors.HexColor('#0F172A'), spaceBefore=6, spaceAfter=2.5),
        'SectionH2': ParagraphStyle('SectionH2', parent=styles['Heading3'], fontName='Helvetica-Bold', fontSize=9, leading=12, textColor=colors.HexColor('#1E293B'), spaceBefore=3.5, spaceAfter=1.5),
        'Body': ParagraphStyle('BodyCustom', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=11, textColor=colors.HexColor('#334155'), spaceAfter=2),
        'BodyBold': ParagraphStyle('BodyBoldCustom', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, leading=11, textColor=colors.HexColor('#0F172A')),
        'Bullet': ParagraphStyle('BulletCustom', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=11, textColor=colors.HexColor('#334155'), leftIndent=8, spaceAfter=1.5),
        'CalloutText': ParagraphStyle('CalloutText', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=11, textColor=colors.HexColor('#1E293B')),
        'TableHeader': ParagraphStyle('TableHeader', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7.5, leading=10, textColor=colors.HexColor('#FFFFFF'), alignment=TA_CENTER),
        'TableCell': ParagraphStyle('TableCell', parent=styles['Normal'], fontName='Helvetica', fontSize=7.5, leading=10, textColor=colors.HexColor('#1E293B')),
        'TableCellBold': ParagraphStyle('TableCellBold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7.5, leading=10, textColor=colors.HexColor('#0F172A')),
        'ChatUser': ParagraphStyle('ChatUser', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7.5, leading=10, textColor=colors.HexColor('#065F46')),
        'ChatBot': ParagraphStyle('ChatBot', parent=styles['Normal'], fontName='Helvetica', fontSize=7.5, leading=10, textColor=colors.HexColor('#0F172A')),
        'ChatBtn': ParagraphStyle('ChatBtn', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7, leading=9, textColor=colors.HexColor('#1E40AF'), alignment=TA_CENTER),
        'ChatMeta': ParagraphStyle('ChatMeta', parent=styles['Normal'], fontName='Helvetica-Oblique', fontSize=6.5, leading=8.5, textColor=colors.HexColor('#64748B'))
    }
    return custom_styles


def build_callout(text, title=None, color_hex="#2563EB", bg_hex="#EFF6FF", border_hex="#BFDBFE"):
    styles = get_styles()
    content = []
    if title:
        content.append(Paragraph(f"<b><font color='{color_hex}'>{title}</font></b>", styles['SectionH2']))
        content.append(Spacer(1, 1))
    content.append(Paragraph(text, styles['CalloutText']))
    t = Table([[content]], colWidths=[USABLE_WIDTH])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor(bg_hex)),
        ('BOX', (0,0), (-1,-1), 0.75, colors.HexColor(border_hex)),
        ('LINELEFT', (0,0), (0,0), 3.5, colors.HexColor(color_hex)),
        ('PADDING', (0,0), (-1,-1), 4.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3.5),
    ]))
    return t


def build_chat_bubble(sender, text, buttons=None, note=None, is_user=False):
    styles = get_styles()
    flowables = []

    if is_user:
        header_p = Paragraph(f"👤 <b>YOU (WhatsApp Reply)</b>", styles['ChatUser'])
        body_p = Paragraph(f"<b>\"{text}\"</b>", styles['ChatUser'])
        t_data = [[header_p], [body_p]]
        t = Table(t_data, colWidths=[4.2 * inch])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#DCFCE7")),
            ('BOX', (0,0), (-1,-1), 0.75, colors.HexColor("#86EFAC")),
            ('PADDING', (0,0), (-1,-1), 3.5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2.5),
        ]))
        outer_table = Table([["", t]], colWidths=[3.2 * inch, 4.3 * inch])
        outer_table.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'RIGHT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('PADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ]))
        flowables.append(outer_table)
    else:
        header_p = Paragraph(f"🤖 <b>TAGONESWA FLEET BOT</b>", styles['BodyBold'])
        body_html = text.replace("\n", "<br/>")
        body_p = Paragraph(body_html, styles['ChatBot'])
        t_rows = [[header_p], [body_p]]

        if buttons:
            btn_cells = []
            for b in buttons:
                btn_p = Paragraph(f"<b>[ {b} ]</b>", styles['ChatBtn'])
                btn_cells.append(btn_p)
            btn_width = (4.8 / len(buttons)) * inch
            btn_table = Table([btn_cells], colWidths=[btn_width] * len(buttons))
            btn_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#EFF6FF")),
                ('BOX', (0,0), (-1,-1), 0.75, colors.HexColor("#93C5FD")),
                ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#BFDBFE")),
                ('PADDING', (0,0), (-1,-1), 2.5),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ]))
            t_rows.append([btn_table])

        if note:
            note_p = Paragraph(f"<i>📌 Action Note: {note}</i>", styles['ChatMeta'])
            t_rows.append([note_p])

        t = Table(t_rows, colWidths=[5.0 * inch])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
            ('BOX', (0,0), (-1,-1), 0.75, colors.HexColor("#CBD5E1")),
            ('PADDING', (0,0), (-1,-1), 3.5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2.5),
        ]))
        outer_table = Table([[t, ""]], colWidths=[5.1 * inch, 2.4 * inch])
        outer_table.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('PADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ]))
        flowables.append(outer_table)

    return flowables


def build_checklist_card(items):
    styles = get_styles()
    rows = [[Paragraph("<b>#</b>", styles['TableHeader']), Paragraph("<b>Training Checklist Item</b>", styles['TableHeader']), Paragraph("<b>Verified</b>", styles['TableHeader'])]]
    for i, itm in enumerate(items, 1):
        rows.append([
            Paragraph(f"<b>{i}</b>", styles['TableCellBold']),
            Paragraph(itm, styles['TableCell']),
            Paragraph("☐ Passed", styles['TableCellBold'])
        ])
    t = Table(rows, colWidths=[0.35 * inch, 6.25 * inch, 0.9 * inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E293B")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor("#FFFFFF"), colors.HexColor("#F8FAFC")]),
        ('PADDING', (0,0), (-1,-1), 2.5),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    return t


def build_header_card(title, role_code, audience, badge_color="#2563EB"):
    styles = get_styles()
    t = Table([
        [
            Paragraph(f"<b>TAGONESWA HOLDINGS • SALES TO FLEET TRAINING MANUAL</b>", styles['DocSubTitle']),
            Paragraph(f"<b><font color='{badge_color}'>{role_code}</font></b>", ParagraphStyle('HRight', parent=styles['Normal'], alignment=TA_RIGHT, fontSize=8, fontName='Helvetica-Bold'))
        ],
        [
            Paragraph(f"<b>{title}</b>", styles['DocTitle']),
            ""
        ],
        [
            Paragraph(f"<b>Audience:</b> {audience} &nbsp;|&nbsp; <b>Bot Number:</b> +91 93282 95424 &nbsp;|&nbsp; <b>Confidentiality:</b> Internal Staff Only", styles['Body']),
            ""
        ]
    ], colWidths=[5.6 * inch, 1.9 * inch])
    t.setStyle(TableStyle([
        ('SPAN', (0,1), (1,1)),
        ('SPAN', (0,2), (1,2)),
        ('PADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
    ]))
    return t


# =========================================================================
# GUIDE 1: SALES REPRESENTATIVE
# =========================================================================
def generate_sales_rep_guide():
    filename = "Sales_to_Fleet_Training_Guide_1_Sales_Representative.pdf"
    doc = SimpleDocTemplate(filename, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = get_styles()
    story = []

    story.append(build_header_card("Sales Representative: Trip Approval & Allowances", "ROLE GUIDE #1", "All Sales Reps across LG Plast, Tagoneswa Hardware & Kreckle Foods"))
    story.append(Spacer(1, 3))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E2E8F0"), spaceAfter=5))

    story.append(Paragraph("1. Role Overview & Commercial Responsibilities", styles['SectionH1']))
    story.append(Paragraph("As a Sales Representative, you initiate delivery dispatches for customer orders. Your actions ensure that orders meet required transport revenue thresholds and operational allowances are accurately budgeted.", styles['Body']))
    story.append(Paragraph("• <b>Stage 1: Trip Initiation</b>: Submit your Favlogix Trip ID and review shortfall calculations.", styles['Bullet']))
    story.append(Paragraph("• <b>Stage 2: Customer Transport Billing</b>: Bill the customer in Favlogix and link the Packaging List Transport Charge ID.", styles['Bullet']))
    story.append(Paragraph("• <b>Stage 3.5: Allowance Estimation</b>: Enter crew, estimated departure/return time, and toll gate expenses for management approval.", styles['Bullet']))
    story.append(Paragraph("• <b>Trip Tracking</b>: Receive instant WhatsApp updates when the vehicle departs, returns, and closes.", styles['Bullet']))
    story.append(Spacer(1, 3))

    story.append(build_callout(
        "<b>Company Auto-Detection:</b> The bot automatically identifies whether you represent <b>LG Plast</b>, <b>Tagoneswa Hardware</b>, or <b>Kreckle Foods</b> based on your registered mobile number. You do not need to manually select your company.<br/>"
        "<b>Clean Commercial View:</b> The bot displays your Total Sales Revenue and Transport Fee. Internal route minimums and calculation formulas are kept confidential.",
        title="Key Commercial Rules", color_hex="#2563EB", bg_hex="#EFF6FF", border_hex="#93C5FD"
    ))
    story.append(Spacer(1, 4))

    story.append(Paragraph("2. Step-by-Step WhatsApp Flow & Dialogue", styles['SectionH1']))
    story.extend(build_chat_bubble("User", "Fleet Approval", is_user=True, note="Step 1: Rep taps [ 🚛 Fleet Approval ]."))
    story.extend(build_chat_bubble(
        "Bot",
        "🚛 *TAGONESWA HARDWARE - FLEET APPROVAL*\n────────────────────\n"
        "Please enter the *Trip ID* from Favlogix (e.g. `TRIP-2026-088`):",
        note="Bot auto-detects company and requests Trip ID."
    ))
    story.extend(build_chat_bubble("User", "TRIP-2026-088", is_user=True, note="Step 2: Rep replies with Trip ID."))
    story.extend(build_chat_bubble(
        "Bot",
        "📋 *TRIP VERIFICATION: TRIP-2026-088*\n────────────────────\n"
        "Destination: *Gweru*\n"
        "Total Sales Value: *$14,200.00*\n"
        "Transport Fee to Take: *$152.00*\n────────────────────\n"
        "Please choose the transport charge option:",
        buttons=["Full Charge", "Partial Charge", "Add to Pending"],
        note="Clean commercial breakdown without formulas."
    ))
    story.extend(build_chat_bubble("User", "Full Charge", is_user=True, note="Step 3: Rep selects [ Full Charge ]."))
    story.extend(build_chat_bubble(
        "Bot",
        "⚠️ *CUSTOMER TRANSPORT CHARGE REQUIRED*\n────────────────────\n"
        "Required Transport Fee: *$152.00*\n\n"
        "Please charge all customers in Favlogix and select *YES* when done:",
        buttons=["YES", "NO"],
        note="Rep bills customers in Favlogix ERP."
    ))
    story.extend(build_chat_bubble("User", "YES", is_user=True, note="Step 4: Rep confirms billing."))
    story.extend(build_chat_bubble(
        "Bot",
        "📦 *TRANSPORT CHARGE ID (PACKAGING LIST)*\n────────────────────\n"
        "Please enter the Transport Charge ID generated on your Favlogix Packaging List (e.g. `mtrtc` or `tc-102`):",
        note="Bot requests Packaging List charge reference."
    ))
    story.extend(build_chat_bubble("User", "mtrtc-gweru", is_user=True, note="Step 5: Rep enters Transport Charge ID."))
    story.extend(build_chat_bubble(
        "Bot",
        "✅ *FLEET TRIP APPROVED & DISPATCHED*\n────────────────────\n"
        "Trip ID: *TRIP-2026-088*\n"
        "Schedules Created: 2 Customer Manifests Registered\n────────────────────\n"
        "Handoff sent to Logistics Supervisor (Edward) for vehicle and driver allocation.",
        note="Handoff to Logistics Supervisor."
    ))
    story.append(Spacer(1, 4))

    story.append(Paragraph("3. Operational Allowances Entry (After Vehicle Allocation)", styles['SectionH1']))
    story.append(Paragraph("Once Edward assigns the truck and driver, the bot alerts you to configure the journey budget:", styles['Body']))
    story.extend(build_chat_bubble(
        "Bot",
        "⚙️ *CONFIGURE TRIP ALLOWANCES: TRIP-2026-088*\n────────────────────\n"
        "Driver: *Terrence Mupfumi* | Truck: *ZW 123 ABC*\n\n"
        "Please enter the *Crew Count* (total staff traveling, e.g. `2`):",
        note="Bot prompts for crew count."
    ))
    story.extend(build_chat_bubble("User", "2", is_user=True))
    story.extend(build_chat_bubble("Bot", "⏰ Please enter expected *Departure Time* (e.g. `06:30 AM`):"))
    story.extend(build_chat_bubble("User", "06:30 AM", is_user=True))
    story.extend(build_chat_bubble("Bot", "🏁 Please enter expected *Return Time* (e.g. `08:00 PM` or `Tomorrow 12:00 PM`):"))
    story.extend(build_chat_bubble("User", "08:00 PM", is_user=True))
    story.extend(build_chat_bubble("Bot", "🛣️ Please enter estimated *Toll Gates Cost* in USD (e.g. `24.00`):"))
    story.extend(build_chat_bubble("User", "24.00", is_user=True))
    story.extend(build_chat_bubble(
        "Bot",
        "📋 *ALLOWANCE SUMMARY: TRIP-2026-088*\n────────────────────\n"
        "• Crew: 2 persons\n"
        "• Meals: 3 meals/person ($2.00 rate) = *$12.00*\n"
        "• Accommodation: *$0.00* (Same-day return)\n"
        "• Toll Gates: *$24.00*\n────────────────────\n"
        "💰 *Total Allowance: $36.00*\n\n"
        "Tap below to submit for Zayn's authorization:",
        buttons=["Submit Allowances", "Edit Details"],
        note="Food allowance rate ($2.00/meal) automatically applied."
    ))
    story.append(Spacer(1, 4))

    story.append(Paragraph("4. Interactive Button Reference", styles['SectionH1']))
    btn_table_data = [
        [Paragraph("Button Title", styles['TableHeader']), Paragraph("Stage / Prompt", styles['TableHeader']), Paragraph("System Action & Next Step", styles['TableHeader'])],
        [Paragraph("<b>[ Full Charge ]</b>", styles['TableCellBold']), Paragraph("Stage 1: Shortfall Card", styles['TableCell']), Paragraph("Full transport fee is billed to customer packaging list in ERP.", styles['TableCell'])],
        [Paragraph("<b>[ Partial Charge ]</b>", styles['TableCellBold']), Paragraph("Stage 1: Shortfall Card", styles['TableCell']), Paragraph("Allows charging partial customer fee; balance logged to debt ledger.", styles['TableCell'])],
        [Paragraph("<b>[ Add to Pending ]</b>", styles['TableCellBold']), Paragraph("Stage 1: Shortfall Card", styles['TableCell']), Paragraph("Defers charge to sales rep debt balance for executive audit review.", styles['TableCell'])],
        [Paragraph("<b>[ YES ]</b>", styles['TableCellBold']), Paragraph("Stage 2: ERP Confirmation", styles['TableCell']), Paragraph("Confirms invoices are posted in Favlogix; requests Transport Charge ID.", styles['TableCell'])],
        [Paragraph("<b>[ Submit Allowances ]</b>", styles['TableCellBold']), Paragraph("Stage 3.5: Allowance Summary", styles['TableCell']), Paragraph("Dispatches allowance request to Logistics Manager (Zayn) for approval.", styles['TableCell'])],
    ]
    t_btn = Table(btn_table_data, colWidths=[1.8 * inch, 1.8 * inch, 3.9 * inch])
    t_btn.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E293B")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor("#FFFFFF"), colors.HexColor("#F8FAFC")]),
        ('PADDING', (0,0), (-1,-1), 3),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(t_btn)
    story.append(Spacer(1, 4))

    story.append(Paragraph("5. Trainer Checklist for Sales Reps", styles['SectionH1']))
    checklist = [
        "Rep can locate bot on WhatsApp (+91 93282 95424) and initiate Fleet Approval.",
        "Rep understands company is auto-detected and does not need manual selection.",
        "Rep accurately enters Favlogix Trip ID and selects correct Shortfall option.",
        "Rep posts transport charge in Favlogix and provides correct Packaging List ID.",
        "Rep accurately configures crew count, departure time, return time, and toll budget."
    ]
    story.append(build_checklist_card(checklist))

    canvas_maker = lambda *args, **kwargs: NumberedCanvas(*args, role_title="GUIDE 1: SALES REPRESENTATIVE", **kwargs)
    doc.build(story, canvasmaker=canvas_maker)
    print(f"Generated: {filename}")


# =========================================================================
# GUIDE 2: LOGISTICS SUPERVISOR (EDWARD)
# =========================================================================
def generate_supervisor_guide():
    filename = "Sales_to_Fleet_Training_Guide_2_Logistics_Supervisor_Edward.pdf"
    doc = SimpleDocTemplate(filename, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = get_styles()
    story = []

    story.append(build_header_card("Logistics Supervisor: Vehicle & Driver Allocation", "ROLE GUIDE #2", "Logistics Supervisor (Edward Chemhere: +263 71 502 5982)"))
    story.append(Spacer(1, 3))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E2E8F0"), spaceAfter=5))

    story.append(Paragraph("1. Role Overview & Fleet Responsibilities", styles['SectionH1']))
    story.append(Paragraph("As the Logistics Supervisor, you manage vehicle allocations and driver dispatches. You ensure that assigned trucks are roadworthy and registered drivers are legally licensed.", styles['Body']))
    story.append(Paragraph("• <b>Stage 3: Fleet Allocation</b>: Check the FIFO queue of approved trips and assign appropriate truck plates and drivers.", styles['Bullet']))
    story.append(Paragraph("• <b>Vehicle Validation</b>: Typed truck plate numbers are validated against the Workshop Fleet Database.", styles['Bullet']))
    story.append(Paragraph("• <b>Driver Auto-Resolution</b>: Typed driver names are validated against active employees; driver mobile numbers are resolved automatically.", styles['Bullet']))
    story.append(Paragraph("• <b>In-Transit Support</b>: Review and approve emergency fuel or repair requests raised during active transit.", styles['Bullet']))
    story.append(Spacer(1, 3))

    story.append(build_callout(
        "<b>Confidentiality Guarantee:</b> Commercial sales totals (order dollar values) are strictly hidden from your view to maintain commercial confidentiality. You will only see the Trip ID, Destination City, Route, and Customer Manifests.<br/>"
        "<b>Queue Command:</b> Type <code>queue</code> or <code>trip queue</code> at any time to inspect pending unallocated trips.",
        title="Supervisor Operational Rules", color_hex="#D97706", bg_hex="#FFFBEB", border_hex="#FDE68A"
    ))
    story.append(Spacer(1, 4))

    story.append(Paragraph("2. Step-by-Step WhatsApp Flow & Dialogue", styles['SectionH1']))
    story.extend(build_chat_bubble(
        "Bot",
        "🔔 *NEW APPROVED TRIP FOR DISPATCH*\n────────────────────\n"
        "Trip ID: *TRIP-2026-088*\n"
        "Company: *Tagoneswa Hardware*\n"
        "Destination: *Gweru*\n"
        "Packaging List Manifests: 2 Deliveries Registered\n────────────────────\n"
        "Please allocate a vehicle and driver:",
        buttons=["Allocate Trip", "Trip Queue"],
        note="Bot alerts Edward immediately after Stage 2."
    ))
    story.extend(build_chat_bubble("User", "Allocate Trip", is_user=True, note="Step 1: Edward taps [ Allocate Trip ]."))
    story.extend(build_chat_bubble(
        "Bot",
        "🚛 *VEHICLE ALLOCATION: TRIP-2026-088*\n────────────────────\n"
        "Please enter the *Truck Plate Number* (e.g. `ZW 123 ABC` or `AGZ 7331`):",
        note="Bot prompts for truck plate (typed response)."
    ))
    story.extend(build_chat_bubble("User", "ZW 123 ABC", is_user=True, note="Step 2: Edward types plate."))
    story.extend(build_chat_bubble(
        "Bot",
        "👤 *DRIVER ALLOCATION: TRIP-2026-088*\n────────────────────\n"
        "Truck: *ZW 123 ABC* (UD Quester 40T - Active ✅)\n\n"
        "Please enter the *Driver's Full Name* (e.g. `Terrence Mupfumi`):",
        note="Bot validates plate against database."
    ))
    story.extend(build_chat_bubble("User", "Terrence Mupfumi", is_user=True, note="Step 3: Edward types driver name."))
    story.extend(build_chat_bubble(
        "Bot",
        "✅ *FLEET ALLOCATION COMPLETE: TRIP-2026-088*\n────────────────────\n"
        "• Truck: *ZW 123 ABC*\n"
        "• Driver: *Terrence Mupfumi* (+263 78 811 2771 ✅)\n────────────────────\n"
        "Trip handed off to Sales Rep to configure journey allowances.",
        note="Driver phone auto-resolved from staff directory."
    ))
    story.append(Spacer(1, 4))

    story.append(Paragraph("3. Emergency Transit Approvals (During Journey)", styles['SectionH1']))
    story.append(Paragraph("If a driver experiences a mechanical fault, tyre puncture, or needs emergency fuel:", styles['Body']))
    story.extend(build_chat_bubble(
        "Bot",
        "⚠️ *EMERGENCY EXPENSE REQUEST: TRIP-2026-088*\n────────────────────\n"
        "Driver: *Terrence Mupfumi*\n"
        "Category: *EMERGENCY FUEL*\n"
        "Requested Amount: *$25.00*\n"
        "Details: Additional diesel for return hill climb\n────────────────────\n"
        "Please approve or decline:",
        buttons=["Approve Expense", "Reject Expense"],
        note="Immediate supervisor review."
    ))
    story.extend(build_chat_bubble("User", "Approve Expense", is_user=True))
    story.extend(build_chat_bubble("Bot", "✅ *Emergency expense of $25.00 APPROVED.* Driver notified to retain receipt."))
    story.append(Spacer(1, 4))

    story.append(Paragraph("4. Interactive Button Reference", styles['SectionH1']))
    btn_table_data = [
        [Paragraph("Button / Command", styles['TableHeader']), Paragraph("Context", styles['TableHeader']), Paragraph("System Action & Next Step", styles['TableHeader'])],
        [Paragraph("<b>[ Trip Queue ]</b> / <code>queue</code>", styles['TableCellBold']), Paragraph("Daily Shift", styles['TableCell']), Paragraph("Displays all pending trips awaiting vehicle allocation in FIFO order.", styles['TableCell'])],
        [Paragraph("<b>[ Allocate Trip ]</b>", styles['TableCellBold']), Paragraph("New Trip Alert", styles['TableCell']), Paragraph("Starts 2-step allocation prompt: Truck Plate then Driver Name.", styles['TableCell'])],
        [Paragraph("<b>[ Approve Expense ]</b>", styles['TableCellBold']), Paragraph("Emergency Alert", styles['TableCell']), Paragraph("Authorizes emergency fuel/repair expenditure; driver instructed to keep slip.", styles['TableCell'])],
        [Paragraph("<b>[ Reject Expense ]</b>", styles['TableCellBold']), Paragraph("Emergency Alert", styles['TableCell']), Paragraph("Declines expenditure; prompts driver to contact logistics dispatch.", styles['TableCell'])],
    ]
    t_btn = Table(btn_table_data, colWidths=[1.8 * inch, 1.8 * inch, 3.9 * inch])
    t_btn.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E293B")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor("#FFFFFF"), colors.HexColor("#F8FAFC")]),
        ('PADDING', (0,0), (-1,-1), 3),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(t_btn)
    story.append(Spacer(1, 4))

    story.append(Paragraph("5. Trainer Checklist for Logistics Supervisor", styles['SectionH1']))
    checklist = [
        "Supervisor understands how to view and navigate FIFO unallocated trip queue.",
        "Supervisor enters valid truck plates matching company workshop inventory.",
        "Supervisor enters registered driver names to trigger automatic phone number resolution.",
        "Supervisor knows how to approve or reject driver emergency transit expenses promptly."
    ]
    story.append(build_checklist_card(checklist))

    canvas_maker = lambda *args, **kwargs: NumberedCanvas(*args, role_title="GUIDE 2: LOGISTICS SUPERVISOR", **kwargs)
    doc.build(story, canvasmaker=canvas_maker)
    print(f"Generated: {filename}")


# =========================================================================
# GUIDE 3: LOGISTICS MANAGER (ZAYN)
# =========================================================================
def generate_manager_guide():
    filename = "Sales_to_Fleet_Training_Guide_3_Logistics_Manager_Zayn.pdf"
    doc = SimpleDocTemplate(filename, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = get_styles()
    story = []

    story.append(build_header_card("Logistics Manager: Governance & Adjudication", "ROLE GUIDE #3", "Logistics Operations Manager (Zayn: +263 71 386 6223)"))
    story.append(Spacer(1, 3))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E2E8F0"), spaceAfter=5))

    story.append(Paragraph("1. Role Overview & Executive Governance", styles['SectionH1']))
    story.append(Paragraph("As the Logistics Manager, you exercise executive control over fleet expenditure and trip closeout. You authorize trip budgets before vehicles depart and adjudicate physical balancing reconciliation upon return.", styles['Body']))
    story.append(Paragraph("• <b>Stage 4: Allowance Approval</b>: Review calculated trip budgets (meals, tolls, accommodation). Approve or request recalculation.", styles['Bullet']))
    story.append(Paragraph("• <b>Budget Recalculation Loop</b>: Enter correction notes sent directly back to the Sales Rep to adjust budgets.", styles['Bullet']))
    story.append(Paragraph("• <b>Stage 7: Final Adjudication</b>: Review the post-trip balancing summary (mileage run, fuel slips, toll receipts, discrepancy balance).", styles['Bullet']))
    story.append(Paragraph("• <b>Confidential Trip Closed Broadcast</b>: Trigger twin broadcasts: operational summary to field staff (sales revenue hidden) and executive audit to master group.", styles['Bullet']))
    story.append(Spacer(1, 3))

    story.append(build_callout(
        "<b>Two-Tiered Broadcast Protection:</b> When you tap <b>[ Authorize & Close Trip ]</b>, the bot automatically strips commercial sales totals from all operational notifications sent to drivers, reps, and supervisors.<br/>"
        "<b>Recalculation Flexibility:</b> If a trip budget has excessive toll estimates or incorrect crew, tap <b>[ Recalculate ]</b> and type your reason. The bot instantly resets the rep's budget form with your guidance.",
        title="Manager Governance Rules", color_hex="#059669", bg_hex="#ECFDF5", border_hex="#A7F3D0"
    ))
    story.append(Spacer(1, 4))

    story.append(Paragraph("2. Stage 4 WhatsApp Flow: Allowance Approval", styles['SectionH1']))
    story.extend(build_chat_bubble(
        "Bot",
        "📋 *TRIP ALLOWANCE APPROVAL: TRIP-2026-088*\n────────────────────\n"
        "Company: *Tagoneswa Hardware* | Destination: *Gweru*\n"
        "Driver: *Terrence Mupfumi* | Truck: *ZW 123 ABC*\n"
        "• Crew Count: 2 persons\n"
        "• Departure: 06:30 AM | Return: 08:00 PM\n"
        "• Meals: 3 meals/person ($2.00 rate) = *$12.00*\n"
        "• Accommodation: *$0.00* (Same-day return)\n"
        "• Toll Gates: *$24.00*\n────────────────────\n"
        "💰 *Total Allowance Requested: $36.00*\n\n"
        "Please review and authorize:",
        buttons=["Approve Allowance", "Recalculate"],
        note="Zayn reviews budget."
    ))
    story.extend(build_chat_bubble("User", "Approve Allowance", is_user=True, note="Zayn taps [ Approve Allowance ]."))
    story.extend(build_chat_bubble(
        "Bot",
        "✅ *ALLOWANCE APPROVED & FORWARDED TO ACCOUNTS*\n────────────────────\n"
        "Trip ID: *TRIP-2026-088* | Total: *$36.00*\n"
        "Notification dispatched to Accounts team for immediate payout.",
        note="Auto-routed to Accounts for transfer."
    ))
    story.append(Spacer(1, 4))

    story.append(Paragraph("3. Stage 7 WhatsApp Flow: Trip Adjudication & Closure", styles['SectionH1']))
    story.append(Paragraph("After driver returns and Sales Admin completes physical balancing:", styles['Body']))
    story.extend(build_chat_bubble(
        "Bot",
        "🏁 *TRIP ADJUDICATION REQUIRED: TRIP-2026-088*\n────────────────────\n"
        "Driver: *Terrence Mupfumi* | Truck: *ZW 123 ABC*\n"
        "• Total Distance Run: *380.0 KM* (Verified 📸)\n"
        "• Total Allowance Disbursed: *$36.00*\n"
        "• Emergency Expenses: *$25.00* (Emergency fuel)\n"
        "• Balancing Status: *BALANCED* by Christine Chiweshe\n"
        "• Discrepancy Amount: *$0.00*\n────────────────────\n"
        "Please authorize final trip closeout:",
        buttons=["Authorize & Close Trip", "Flag Audit"],
        note="Comprehensive post-journey audit report."
    ))
    story.extend(build_chat_bubble("User", "Authorize & Close Trip", is_user=True))
    story.extend(build_chat_bubble(
        "Bot",
        "🔒 *TRIP PERMANENTLY CLOSED*\n────────────────────\n"
        "Trip ID: *TRIP-2026-088*\n"
        "All ledgers finalized. Twin broadcasts dispatched with complete sales confidentiality.",
        note="Operational broadcast strips sales values."
    ))
    story.append(Spacer(1, 4))

    story.append(Paragraph("4. Interactive Button Reference", styles['SectionH1']))
    btn_table_data = [
        [Paragraph("Button Title", styles['TableHeader']), Paragraph("Workflow Stage", styles['TableHeader']), Paragraph("System Action & Next Step", styles['TableHeader'])],
        [Paragraph("<b>[ Approve Allowance ]</b>", styles['TableCellBold']), Paragraph("Stage 4: Allowance Review", styles['TableCell']), Paragraph("Authorizes journey budget and forwards notification to Accounts for cash/transfer payout.", styles['TableCell'])],
        [Paragraph("<b>[ Recalculate ]</b>", styles['TableCellBold']), Paragraph("Stage 4: Allowance Review", styles['TableCell']), Paragraph("Prompts Zayn for adjustment note and resets allowance step for Sales Rep.", styles['TableCell'])],
        [Paragraph("<b>[ Authorize & Close Trip ]</b>", styles['TableCellBold']), Paragraph("Stage 7: Final Adjudication", styles['TableCell']), Paragraph("Permanently closes trip record; dispatches operational and executive audit broadcasts.", styles['TableCell'])],
        [Paragraph("<b>[ Flag Audit ]</b>", styles['TableCellBold']), Paragraph("Stage 7: Final Adjudication", styles['TableCell']), Paragraph("Holds trip in Pending Review state and notifies Executive Observers for audit investigation.", styles['TableCell'])],
    ]
    t_btn = Table(btn_table_data, colWidths=[1.8 * inch, 1.8 * inch, 3.9 * inch])
    t_btn.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E293B")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor("#FFFFFF"), colors.HexColor("#F8FAFC")]),
        ('PADDING', (0,0), (-1,-1), 3),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(t_btn)
    story.append(Spacer(1, 4))

    story.append(Paragraph("5. Trainer Checklist for Logistics Manager", styles['SectionH1']))
    checklist = [
        "Manager verifies crew size and meal calculations ($2.00/person/meal).",
        "Manager understands how to send recalculation feedback notes back to Sales Reps.",
        "Manager reviews physical balancing summaries including odometer km and receipts.",
        "Manager confirms that closing trips triggers confidential broadcasts protecting sales totals."
    ]
    story.append(build_checklist_card(checklist))

    canvas_maker = lambda *args, **kwargs: NumberedCanvas(*args, role_title="GUIDE 3: LOGISTICS MANAGER", **kwargs)
    doc.build(story, canvasmaker=canvas_maker)
    print(f"Generated: {filename}")


# =========================================================================
# GUIDE 4: ACCOUNTS & FINANCE
# =========================================================================
def generate_accounts_guide():
    filename = "Sales_to_Fleet_Training_Guide_4_Accounts_Finance.pdf"
    doc = SimpleDocTemplate(filename, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = get_styles()
    story = []

    story.append(build_header_card("Accounts & Finance: Allowance Disbursement", "ROLE GUIDE #4", "Accounts Team (Vigilance Bangezhano & Munashe Milca)"))
    story.append(Spacer(1, 3))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E2E8F0"), spaceAfter=5))

    story.append(Paragraph("1. Role Overview & Financial Responsibilities", styles['SectionH1']))
    story.append(Paragraph("As the Accounts & Finance officer, you disburse approved journey allowances to drivers. Your prompt disbursement ensures that transport trips depart on schedule without delay.", styles['Body']))
    story.append(Paragraph("• <b>Stage 4: Allowance Payout</b>: Receive authorization cards after Zayn approves the budget.", styles['Bullet']))
    story.append(Paragraph("• <b>Driver Payout Verification</b>: Verify driver identity, truck plate, and total amount (food, tolls, accommodation).", styles['Bullet']))
    story.append(Paragraph("• <b>Payment Disbursement</b>: Disburse funds via Ecocash, cash, or internal petty cash transfer.", styles['Bullet']))
    story.append(Paragraph("• <b>WhatsApp Confirmation</b>: Tap <b>[ Transfer Done ]</b> on WhatsApp to log disbursement and release the driver for departure.", styles['Bullet']))
    story.append(Spacer(1, 3))

    story.append(build_callout(
        "<b>Single Action Required:</b> Once you disburse funds to the driver, tap <b>[ Transfer Done ]</b> directly in your WhatsApp chat.<br/>"
        "<b>Driver Release:</b> Tapping <b>[ Transfer Done ]</b> triggers the bot to automatically alert the driver that funds are in hand and prompt them to confirm departure time.",
        title="Accounts Operational Protocol", color_hex="#2563EB", bg_hex="#EFF6FF", border_hex="#BFDBFE"
    ))
    story.append(Spacer(1, 4))

    story.append(Paragraph("2. Step-by-Step WhatsApp Flow & Dialogue", styles['SectionH1']))
    story.extend(build_chat_bubble(
        "Bot",
        "💳 *ALLOWANCE PAYMENT AUTHORIZATION*\n────────────────────\n"
        "Trip ID: *TRIP-2026-088*\n"
        "Approved by: *Zayn (Logistics Manager)*\n"
        "Driver: *Terrence Mupfumi* (+263 78 811 2771)\n"
        "Truck: *ZW 123 ABC*\n\n"
        "💰 *AMOUNT TO DISBURSE: $36.00*\n"
        "• Food Allowance: $12.00\n"
        "• Toll Gates Allowance: $24.00\n────────────────────\n"
        "Please transfer funds to driver and confirm below:",
        buttons=["Transfer Done", "Query Details"],
        note="Bot alerts Accounts team immediately upon Zayn's approval."
    ))
    story.extend(build_chat_bubble("User", "Transfer Done", is_user=True, note="Accounts officer taps [ Transfer Done ]."))
    story.extend(build_chat_bubble(
        "Bot",
        "✅ *PAYMENT CONFIRMED: TRIP-2026-088*\n────────────────────\n"
        "Disbursement of *$36.00* recorded successfully.\n"
        "Driver Terrence Mupfumi has been notified and prompted for departure confirmation.",
        note="Trip transitions to TRANSFERRED status."
    ))
    story.append(Spacer(1, 4))

    story.append(Paragraph("3. Interactive Button Reference", styles['SectionH1']))
    btn_table_data = [
        [Paragraph("Button Title", styles['TableHeader']), Paragraph("When Displayed", styles['TableHeader']), Paragraph("System Action & Result", styles['TableHeader'])],
        [Paragraph("<b>[ Transfer Done ]</b>", styles['TableCellBold']), Paragraph("Allowance Payout Card", styles['TableCell']), Paragraph("Logs payment timestamp and authorizer; unlocks driver departure stage in bot.", styles['TableCell'])],
        [Paragraph("<b>[ Query Details ]</b>", styles['TableCellBold']), Paragraph("Allowance Payout Card", styles['TableCell']), Paragraph("Allows entering an inquiry note sent to Zayn if allowance amount requires clarification.", styles['TableCell'])],
    ]
    t_btn = Table(btn_table_data, colWidths=[1.8 * inch, 1.8 * inch, 3.9 * inch])
    t_btn.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E293B")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor("#FFFFFF"), colors.HexColor("#F8FAFC")]),
        ('PADDING', (0,0), (-1,-1), 3),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(t_btn)
    story.append(Spacer(1, 4))

    story.append(Paragraph("4. Trainer Checklist for Accounts", styles['SectionH1']))
    checklist = [
        "Accounts staff verifies Zayn's approval before disbursing funds.",
        "Accounts confirms driver identity and mobile number before payout.",
        "Accounts officer taps [ Transfer Done ] immediately after completing the financial transfer.",
        "Accounts understands that tapping [ Transfer Done ] unlocks the driver departure prompt."
    ]
    story.append(build_checklist_card(checklist))

    canvas_maker = lambda *args, **kwargs: NumberedCanvas(*args, role_title="GUIDE 4: ACCOUNTS & FINANCE", **kwargs)
    doc.build(story, canvasmaker=canvas_maker)
    print(f"Generated: {filename}")


# =========================================================================
# GUIDE 5: COMMERCIAL DRIVER
# =========================================================================
def generate_driver_guide():
    filename = "Sales_to_Fleet_Training_Guide_5_Commercial_Driver.pdf"
    doc = SimpleDocTemplate(filename, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = get_styles()
    story = []

    story.append(build_header_card("Commercial Driver: Transit, Odometers & Safety", "ROLE GUIDE #5", "All 21 Commercial Drivers (Fleet Transport Crew)"))
    story.append(Spacer(1, 3))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E2E8F0"), spaceAfter=5))

    story.append(Paragraph("1. Role Overview & Driver Responsibilities", styles['SectionH1']))
    story.append(Paragraph("As a Commercial Driver, you operate company vehicles and execute deliveries safely. The WhatsApp bot is your co-pilot for logging departure, verifying mileage, and reporting emergency road expenses.", styles['Body']))
    story.append(Paragraph("• <b>Stage 5: Departure Confirmation</b>: Confirm departure time once allowance is received.", styles['Bullet']))
    story.append(Paragraph("• <b>Start Odometer Photo</b>: Snap and send a photo of the vehicle dashboard; AI reads and confirms your mileage.", styles['Bullet']))
    story.append(Paragraph("• <b>In-Transit Support</b>: Report emergency fuel or mechanical breakdown expenses directly via WhatsApp buttons.", styles['Bullet']))
    story.append(Paragraph("• <b>Depot Arrival</b>: Tap <b>[ I Have Returned ]</b> upon arrival and snap a photo of the final Return Odometer.", styles['Bullet']))
    story.append(Paragraph("• <b>Physical Balancing</b>: Proceed to the Sales Admin desk with physical fuel slips and toll gate receipts.", styles['Bullet']))
    story.append(Spacer(1, 3))

    story.append(build_callout(
        "<b>Clear Photo Guidelines:</b> When taking odometer photos, turn on your vehicle cabin light if it is dark, wipe the dashboard glass, and capture the odometer numbers clearly. The AI will read the mileage instantly.<br/>"
        "<b>Anti-Hijacking Security:</b> Sending live location pins over WhatsApp is disabled for cargo protection and your personal safety.",
        title="Driver Safety & Photo Protocol", color_hex="#059669", bg_hex="#ECFDF5", border_hex="#A7F3D0"
    ))
    story.append(Spacer(1, 4))

    story.append(Paragraph("2. Step-by-Step WhatsApp Flow & Dialogue", styles['SectionH1']))
    story.extend(build_chat_bubble(
        "Bot",
        "🚛 *TRIP DISPATCH READY: TRIP-2026-088*\n────────────────────\n"
        "Truck: *ZW 123 ABC* | Route: *Harare -> Gweru*\n"
        "Allowance: *$36.00* transferred to your account.\n\n"
        "Please reply with your confirmed *Departure Time* (e.g. `06:30 AM`):",
        note="Bot prompts driver for departure time."
    ))
    story.extend(build_chat_bubble("User", "06:30 AM", is_user=True))
    story.extend(build_chat_bubble(
        "Bot",
        "🚚 *TRIP DEPARTURE: TRIP-2026-088*\n────────────────────\n"
        "📸 *Please take and send a photo of the vehicle's dashboard / Starting Odometer:*\n\n"
        "_(Our AI will automatically verify your starting mileage from the photo)._",
        note="Driver snaps dashboard photo."
    ))
    story.extend(build_chat_bubble("User", "📷 [Photo of Dashboard Instrument Cluster]", is_user=True))
    story.extend(build_chat_bubble(
        "Bot",
        "📸 *ODOMETER DETECTED: 145,200 KM*\n────────────────────\n"
        "We detected *145,200 KM* from your dashboard photo.\n\n"
        "Tap below to confirm, or reply with correct numbers if different:",
        buttons=["✅ Confirm Reading", "✏️ Enter Manually"],
        note="AI reads odometer; driver taps confirm."
    ))
    story.extend(build_chat_bubble("User", "✅ Confirm Reading", is_user=True))
    story.extend(build_chat_bubble(
        "Bot",
        "✅ *TRIP STARTED: TRIP-2026-088*\n────────────────────\n"
        "Start Odometer: *145,200 KM*\n"
        "Drive safely! Please report emergency expenses as needed, and tap 'I Have Returned' upon depot arrival.",
        buttons=["Emergency Charges", "I Have Returned"],
        note="Live transit menu active during journey."
    ))
    story.append(Spacer(1, 4))

    story.append(Paragraph("3. Reporting Emergency Expenses & Depot Arrival", styles['SectionH1']))
    story.extend(build_chat_bubble("User", "Emergency Charges", is_user=True, note="Driver needs emergency fuel."))
    story.extend(build_chat_bubble(
        "Bot",
        "⚠️ *EMERGENCY CHARGES: TRIP-2026-088*\n────────────────────\n"
        "Please select the emergency charge type:",
        buttons=["Emergency Fuel", "Other (Repairs)"],
        note="Driver selects Fuel or Repairs."
    ))
    story.extend(build_chat_bubble("User", "Emergency Fuel", is_user=True))
    story.extend(build_chat_bubble("Bot", "⛽ Please enter the *Emergency Fuel Amount* in USD (e.g. `25.00`):"))
    story.extend(build_chat_bubble("User", "25.00", is_user=True))
    story.extend(build_chat_bubble("Bot", "✅ Emergency fuel request of $25.00 sent to Logistics Supervisor for immediate review."))
    story.append(Spacer(1, 3))

    story.append(Paragraph("Depot Arrival & Return Odometer Verification:", styles['SectionH2']))
    story.extend(build_chat_bubble("User", "I Have Returned", is_user=True, note="Driver returns to Harare depot."))
    story.extend(build_chat_bubble(
        "Bot",
        "🏁 *DEPOT ARRIVAL: TRIP-2026-088*\n────────────────────\n"
        "📸 *Please take and send a photo of the vehicle's dashboard / Return Odometer:*",
        note="Driver snaps final return dashboard photo."
    ))
    story.extend(build_chat_bubble("User", "📷 [Photo of Return Odometer]", is_user=True))
    story.extend(build_chat_bubble(
        "Bot",
        "🏁 *RETURN ODOMETER CONFIRMED: 145,580 KM*\n────────────────────\n"
        "• Start Odometer: 145,200 KM\n"
        "• Return Odometer: 145,580 KM\n"
        "• Total Distance: *380.0 KM*\n────────────────────\n"
        "Please proceed to the Sales Admin desk with all physical receipts for balancing.",
        note="Bot calculates total trip distance run."
    ))
    story.append(Spacer(1, 4))

    story.append(Paragraph("4. Interactive Button Reference", styles['SectionH1']))
    btn_table_data = [
        [Paragraph("Button Title", styles['TableHeader']), Paragraph("When Displayed", styles['TableHeader']), Paragraph("System Action & Result", styles['TableHeader'])],
        [Paragraph("<b>[ ✅ Confirm Reading ]</b>", styles['TableCellBold']), Paragraph("AI Odometer Detection", styles['TableCell']), Paragraph("Accepts the AI-verified mileage reading and advances trip status.", styles['TableCell'])],
        [Paragraph("<b>[ ✏️ Enter Manually ]</b>", styles['TableCellBold']), Paragraph("AI Odometer Detection", styles['TableCell']), Paragraph("Allows driver to manually type odometer numbers if photo detection was inaccurate.", styles['TableCell'])],
        [Paragraph("<b>[ Emergency Charges ]</b>", styles['TableCellBold']), Paragraph("Trip In-Transit Menu", styles['TableCell']), Paragraph("Opens prompt to log emergency fuel or breakdown repairs for supervisor approval.", styles['TableCell'])],
        [Paragraph("<b>[ I Have Returned ]</b>", styles['TableCellBold']), Paragraph("Trip In-Transit Menu", styles['TableCell']), Paragraph("Signals safe arrival at depot and requests final Return Odometer photo.", styles['TableCell'])],
    ]
    t_btn = Table(btn_table_data, colWidths=[1.8 * inch, 1.8 * inch, 3.9 * inch])
    t_btn.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E293B")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor("#FFFFFF"), colors.HexColor("#F8FAFC")]),
        ('PADDING', (0,0), (-1,-1), 3),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(t_btn)
    story.append(Spacer(1, 4))

    story.append(Paragraph("5. Trainer Checklist for Commercial Drivers", styles['SectionH1']))
    checklist = [
        "Driver knows how to reply with departure time upon receiving dispatch notice.",
        "Driver takes clear, well-lit photos of dashboard odometer clusters.",
        "Driver understands how to confirm or edit AI-detected odometer readings.",
        "Driver knows how to report emergency fuel or repairs during breakdowns.",
        "Driver taps [ I Have Returned ] upon depot arrival and snaps the final return odometer photo."
    ]
    story.append(build_checklist_card(checklist))

    canvas_maker = lambda *args, **kwargs: NumberedCanvas(*args, role_title="GUIDE 5: COMMERCIAL DRIVER", **kwargs)
    doc.build(story, canvasmaker=canvas_maker)
    print(f"Generated: {filename}")


# =========================================================================
# GUIDE 6: SALES ADMINISTRATOR
# =========================================================================
def generate_sales_admin_guide():
    filename = "Sales_to_Fleet_Training_Guide_6_Sales_Administrator.pdf"
    doc = SimpleDocTemplate(filename, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = get_styles()
    story = []

    story.append(build_header_card("Sales Administrator: Physical Balancing", "ROLE GUIDE #6", "Sales Admins (Everjoy - Kreckle, Onelly & Mazviita - LG, Christine - TG)"))
    story.append(Spacer(1, 3))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E2E8F0"), spaceAfter=5))

    story.append(Paragraph("1. Role Overview & Balancing Responsibilities", styles['SectionH1']))
    story.append(Paragraph("As a company Sales Administrator, you conduct the mandatory physical balancing session with the driver upon their return to the depot. You inspect receipts and verify that all cash collected and operational allowances are reconciled.", styles['Body']))
    story.append(Paragraph("• <b>Stage 6: Physical Balancing</b>: Meet returning drivers at your administration desk.", styles['Bullet']))
    story.append(Paragraph("• <b>Physical Slip Audit</b>: Inspect physical toll gate tickets, fuel receipts, and repair invoices.", styles['Bullet']))
    story.append(Paragraph("• <b>Customer Cash Reconciliation</b>: Reconcile cash collected against delivery packaging lists.", styles['Bullet']))
    story.append(Paragraph("• <b>Discrepancy Logging</b>: Record any shortages or surplus into the system.", styles['Bullet']))
    story.append(Paragraph("• <b>Mark Balanced</b>: Tap <b>[ Balanced ]</b> on WhatsApp or the Web Dashboard to forward the file to Zayn for final closure.", styles['Bullet']))
    story.append(Spacer(1, 3))

    story.append(build_callout(
        "<b>Company Partitioning:</b> Each Sales Admin oversees their dedicated company division (Kreckle Foods, LG Plast, or Tagoneswa Hardware). You will receive return alerts specifically for your company's dispatches.<br/>"
        "<b>Receipt Retention:</b> Drivers must surrender all physical paper receipts. Staple the receipts to the printed packaging manifest before filing.",
        title="Balancing Desk Protocol", color_hex="#D97706", bg_hex="#FFFBEB", border_hex="#FDE68A"
    ))
    story.append(Spacer(1, 4))

    story.append(Paragraph("2. Step-by-Step WhatsApp Flow & Dialogue", styles['SectionH1']))
    story.extend(build_chat_bubble(
        "Bot",
        "↩️ *DRIVER RETURNED TO DEPOT: TRIP-2026-088*\n────────────────────\n"
        "Company: *Tagoneswa Hardware*\n"
        "Driver: *Terrence Mupfumi* | Truck: *ZW 123 ABC*\n"
        "Distance Run: *380.0 KM*\n"
        "Initial Allowance: *$36.00*\n"
        "Emergency Expenses: *$25.00* (Fuel)\n────────────────────\n"
        "Please conduct physical balancing session with driver:",
        buttons=["Balanced", "Log Discrepancy"],
        note="Bot alerts Sales Admin when driver logs return odometer."
    ))
    story.extend(build_chat_bubble("User", "Balanced", is_user=True, note="Sales Admin confirms all slips and cash match."))
    story.extend(build_chat_bubble(
        "Bot",
        "⚖️ *TRIP BALANCED: TRIP-2026-088*\n────────────────────\n"
        "Status: *BALANCED*\n"
        "Audited by: *Christine Chiweshe (Sales Admin)*\n"
        "Discrepancy: *$0.00*\n────────────────────\n"
        "Balancing report forwarded to Logistics Manager (Zayn) for final closure authorization.",
        note="Trip advances to Stage 7 for Zayn's adjudication."
    ))
    story.append(Spacer(1, 4))

    story.append(Paragraph("3. Handling Discrepancies (Shortfall or Missing Slips)", styles['SectionH1']))
    story.append(Paragraph("If a driver lost a toll slip or cash does not balance with manifests:", styles['Body']))
    story.extend(build_chat_bubble("User", "Log Discrepancy", is_user=True))
    story.extend(build_chat_bubble("Bot", "⚠️ Please enter the *Discrepancy Amount* in USD (e.g. `-10.00` for deficit or `+5.00` for surplus):"))
    story.extend(build_chat_bubble("User", "-10.00", is_user=True))
    story.extend(build_chat_bubble("Bot", "📝 Please enter the *Discrepancy Reason / Notes* (e.g. `Missing toll slip at Norton gate`):"))
    story.extend(build_chat_bubble("User", "Missing toll slip at Norton gate", is_user=True))
    story.extend(build_chat_bubble(
        "Bot",
        "⚖️ *DISCREPANCY LOGGED: TRIP-2026-088*\n────────────────────\n"
        "Discrepancy Amount: *-$10.00*\n"
        "Reason: Missing toll slip at Norton gate\n"
        "Forwarded to Logistics Manager (Zayn) for executive adjudication.",
        note="Zayn adjudicates whether to deduct or forgive."
    ))
    story.append(Spacer(1, 4))

    story.append(Paragraph("4. Interactive Button Reference", styles['SectionH1']))
    btn_table_data = [
        [Paragraph("Button Title", styles['TableHeader']), Paragraph("When Displayed", styles['TableHeader']), Paragraph("System Action & Result", styles['TableHeader'])],
        [Paragraph("<b>[ Balanced ]</b>", styles['TableCellBold']), Paragraph("Driver Return Alert", styles['TableCell']), Paragraph("Confirms all receipts and cash match; sets status to BALANCED and notifies Zayn.", styles['TableCell'])],
        [Paragraph("<b>[ Log Discrepancy ]</b>", styles['TableCellBold']), Paragraph("Driver Return Alert", styles['TableCell']), Paragraph("Opens prompt to record shortage/surplus amount and explanatory notes for management audit.", styles['TableCell'])],
    ]
    t_btn = Table(btn_table_data, colWidths=[1.8 * inch, 1.8 * inch, 3.9 * inch])
    t_btn.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E293B")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor("#FFFFFF"), colors.HexColor("#F8FAFC")]),
        ('PADDING', (0,0), (-1,-1), 3),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(t_btn)
    story.append(Spacer(1, 4))

    story.append(Paragraph("5. Trainer Checklist for Sales Administrators", styles['SectionH1']))
    checklist = [
        "Admin receives and monitors depot arrival notifications for their company division.",
        "Admin physically verifies all fuel receipts, toll tickets, and cash collected.",
        "Admin knows how to mark a trip as [ Balanced ] when all records reconcile.",
        "Admin knows how to log discrepancy amounts and reasons when receipts are missing."
    ]
    story.append(build_checklist_card(checklist))

    canvas_maker = lambda *args, **kwargs: NumberedCanvas(*args, role_title="GUIDE 6: SALES ADMINISTRATOR", **kwargs)
    doc.build(story, canvasmaker=canvas_maker)
    print(f"Generated: {filename}")


def main():
    print("==================================================")
    print("GENERATING SALES TO FLEET TRAINING MANUALS (6 ROLES)")
    print("==================================================")
    generate_sales_rep_guide()
    generate_supervisor_guide()
    generate_manager_guide()
    generate_accounts_guide()
    generate_driver_guide()
    generate_sales_admin_guide()
    print("==================================================")
    print("ALL 6 TRAINING GUIDES SUCCESSFULLY GENERATED!")
    print("==================================================")


if __name__ == "__main__":
    main()
