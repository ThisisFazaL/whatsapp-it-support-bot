# -*- coding: utf-8 -*-
"""
Tagoneswa — Complete Sales & Fleet WhatsApp Flow PDF  (Version 2.3)
Updated per user specifications:
- Stage 3: Edward cannot see the total sales amount (Route only, no sales figure).
- Stage 4: Zayn receives the allowance approval prompt. Once Zayn approves, Accounts is notified to handle money transfer.
- Stage 5:
  * When driver starts trip, live location streams to perspective Sales Rep.
  * Driver sees 3 buttons: [Delivery Charges], [Emergency Charges], [I am Returning].
  * Under [Emergency Charges]: [Emergency Fuel], [Other].
    In [Other]: driver types issue, bot asks how much money spent.
  * When driver taps [I am Returning]: live location turns OFF, Sales Rep notified.
  * Driver then sees 2 buttons: [Emergency Charges], [I Have Returned].
  * When driver taps [I Have Returned], assigned Sales Admin is alerted for Stage 6 balancing session.
- System auto-verifies delivery charges using Customer ID schedule registered by Sales Rep in Stage 2.
- Clean text on all buttons (no emojis anywhere).
Run: python generate_sales_fleet_flow_pdf.py
"""
import os
import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfgen import canvas

# ─────────────────────────────────────────────────────────────────────────────
# PAGE DECORATOR
# ─────────────────────────────────────────────────────────────────────────────
class NumberedCanvas(canvas.Canvas):
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
            self._draw(num_pages)
            super().showPage()
        super().save()

    def _draw(self, total):
        self.saveState()
        W, H = letter
        if self._pageNumber > 1:
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.5)
            self.line(54, H - 40, W - 54, H - 40)
            self.setFont("Helvetica-Bold", 7.5)
            self.setFillColor(colors.HexColor("#1E3A8A"))
            self.drawString(54, H - 33, "TAGONESWA HOLDINGS — COMPLETE SALES & FLEET WHATSAPP FLOW")
            self.setFont("Helvetica", 7.5)
            self.setFillColor(colors.HexColor("#64748B"))
            self.drawRightString(W - 54, H - 33, "CONFIDENTIAL INTERNAL DOCUMENT")
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(54, 44, W - 54, 44)
        self.setFont("Helvetica-Bold", 7.5)
        self.setFillColor(colors.HexColor("#475569"))
        self.drawRightString(W - 54, 32, f"Page {self._pageNumber} of {total}")
        self.setFont("Helvetica", 7.5)
        self.drawString(54, 32,
            f"Generated {datetime.datetime.now().strftime('%d %B %Y')}  |  SOP-FLEET-2026  |  Version 2.3")
        self.restoreState()


# ─────────────────────────────────────────────────────────────────────────────
# STYLE FACTORY
# ─────────────────────────────────────────────────────────────────────────────
def _styles():
    base = getSampleStyleSheet()
    def s(name, **kw):
        return ParagraphStyle(name, parent=base["Normal"], **kw)
    return {
        "title":  s("TT", fontName="Helvetica-Bold", fontSize=21, leading=26,
                    textColor=colors.HexColor("#0F172A"), spaceAfter=4),
        "sub":    s("SB", fontName="Helvetica", fontSize=10, leading=14,
                    textColor=colors.HexColor("#2563EB"), spaceAfter=8),
        "h1":     s("H1", fontName="Helvetica-Bold", fontSize=12.5, leading=15,
                    textColor=colors.HexColor("#0F172A"), spaceBefore=12, spaceAfter=4),
        "h2":     s("H2", fontName="Helvetica-Bold", fontSize=10, leading=13,
                    textColor=colors.HexColor("#1E3A8A"), spaceBefore=7, spaceAfter=3),
        "h3":     s("H3", fontName="Helvetica-Bold", fontSize=8.5, leading=11,
                    textColor=colors.HexColor("#374151"), spaceBefore=4, spaceAfter=2),
        "body":   s("BD", fontName="Helvetica", fontSize=8.5, leading=12,
                    textColor=colors.HexColor("#334155"), spaceAfter=3),
        "note":   s("NT", fontName="Helvetica-Oblique", fontSize=8, leading=11,
                    textColor=colors.HexColor("#64748B"), spaceAfter=2),
        "th":     s("TH", fontName="Helvetica-Bold", fontSize=8, leading=10,
                    textColor=colors.white),
        "td":     s("TD", fontName="Helvetica", fontSize=8, leading=11,
                    textColor=colors.HexColor("#1E293B")),
        "tdb":    s("TDB", fontName="Helvetica-Bold", fontSize=8, leading=11,
                    textColor=colors.HexColor("#0F172A")),
    }


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def callout(para, bg="#EFF6FF", border="#BFDBFE"):
    t = Table([[para]], colWidths=[7.0 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), colors.HexColor(bg)),
        ("BOX",           (0,0), (-1,-1), 1, colors.HexColor(border)),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
    ]))
    return t


def rule(story):
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=0.6,
                             color=colors.HexColor("#E2E8F0"), spaceAfter=4))


def stage_banner(title, subtitle, color, story, st):
    data = [[
        Paragraph(f'<font color="white"><b>{title}</b></font>',
                  ParagraphStyle("SH", fontName="Helvetica-Bold", fontSize=10.5,
                                 leading=13, textColor=colors.white)),
        Paragraph(f'<font color="#BFDBFE">{subtitle}</font>',
                  ParagraphStyle("SS", fontName="Helvetica", fontSize=8,
                                 leading=11, textColor=colors.HexColor("#BFDBFE"),
                                 alignment=TA_RIGHT))
    ]]
    t = Table(data, colWidths=[4.2*inch, 2.8*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), colors.HexColor(color)),
        ("TOPPADDING",    (0,0), (-1,-1), 7),
        ("BOTTOMPADDING", (0,0), (-1,-1), 7),
        ("LEFTPADDING",   (0,0), (-1,-1), 9),
        ("RIGHTPADDING",  (0,0), (-1,-1), 9),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(Spacer(1, 8))
    story.append(t)
    story.append(Spacer(1, 5))


def bubble(lines, role_label, role_hex, bg, buttons=None, width=5.2):
    role_p = Paragraph(
        f'<font color="{role_hex}"><b>{role_label}</b></font>',
        ParagraphStyle("RL", fontName="Helvetica-Bold", fontSize=7.5,
                       leading=9.5, textColor=colors.HexColor(role_hex))
    )
    msg_text = "<br/>".join(
        ln.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        for ln in lines
    )
    msg_p = Paragraph(
        msg_text,
        ParagraphStyle("MB", fontName="Courier", fontSize=7.5, leading=10,
                       textColor=colors.HexColor("#0F172A"))
    )
    inner = Table([[msg_p]], colWidths=[width * inch])
    inner.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), colors.HexColor(bg)),
        ("BOX",           (0,0), (-1,-1), 0.8, colors.HexColor("#CBD5E1")),
        ("TOPPADDING",    (0,0), (-1,-1), 4.5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4.5),
        ("LEFTPADDING",   (0,0), (-1,-1), 6.5),
        ("RIGHTPADDING",  (0,0), (-1,-1), 6.5),
    ]))
    elems = [role_p, Spacer(1, 1.5), inner]
    if buttons:
        for btn in buttons[:3]:
            bp = Paragraph(
                f"  [ {btn} ]",
                ParagraphStyle("BT", fontName="Helvetica-Bold", fontSize=7.5,
                               leading=9.5, textColor=colors.HexColor("#1D4ED8"))
            )
            bb = Table([[bp]], colWidths=[width * inch])
            bb.setStyle(TableStyle([
                ("BACKGROUND",    (0,0), (-1,-1), colors.HexColor("#EFF6FF")),
                ("BOX",           (0,0), (-1,-1), 0.8, colors.HexColor("#BFDBFE")),
                ("TOPPADDING",    (0,0), (-1,-1), 2.5),
                ("BOTTOMPADDING", (0,0), (-1,-1), 2.5),
                ("LEFTPADDING",   (0,0), (-1,-1), 5),
                ("RIGHTPADDING",  (0,0), (-1,-1), 5),
            ]))
            elems.append(Spacer(1, 1.5))
            elems.append(bb)
    rows = [[e] for e in elems]
    wrapper = Table(rows, colWidths=[width * inch + 14])
    wrapper.setStyle(TableStyle([
        ("LEFTPADDING",   (0,0), (-1,-1), 0),
        ("RIGHTPADDING",  (0,0), (-1,-1), 0),
        ("TOPPADDING",    (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 2),
    ]))
    return wrapper


def sp(n=3.5):
    return Spacer(1, n)


# ─────────────────────────────────────────────────────────────────────────────
# BUILD SCRIPT
# ─────────────────────────────────────────────────────────────────────────────
def build_pdf(filename="Tagoneswa_Complete_Sales_Fleet_WhatsApp_Flow.pdf"):
    doc = SimpleDocTemplate(
        filename, pagesize=letter,
        leftMargin=54, rightMargin=54,
        topMargin=54, bottomMargin=54
    )
    st = _styles()
    story = []

    # ══════════════════════════════════════════════════════════════════
    # COVER PAGE
    # ══════════════════════════════════════════════════════════════════
    top = Table([[
        Paragraph("TAGONESWA HOLDINGS",
                  ParagraphStyle("CL", fontName="Helvetica-Bold", fontSize=9,
                                 textColor=colors.HexColor("#2563EB"))),
        Paragraph(f"DATE: {datetime.datetime.now().strftime('%d %B %Y')}  |  SOP-FLEET-2026",
                  ParagraphStyle("CR", fontName="Helvetica", fontSize=8,
                                 textColor=colors.HexColor("#64748B"), alignment=TA_RIGHT))
    ]], colWidths=[3.5*inch, 3.5*inch])
    top.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 0),
    ]))
    story.append(top)
    story.append(HRFlowable(width="100%", thickness=1.2,
                             color=colors.HexColor("#2563EB"), spaceAfter=14))

    story.append(Paragraph("Complete Sales &amp; Fleet Operations Flow", st["title"]))
    story.append(Paragraph(
        "Standard Operating Procedures &amp; Live WhatsApp Conversation Walkthrough", st["sub"]))
    story.append(sp(4))
    story.append(callout(Paragraph(
        "<b>System Overview:</b> This document provides the complete, authoritative operational "
        "flow for logistics, fleet dispatch, driver allowances, live location streaming, automated customer payment "
        "verification, and return balancing sessions. Every WhatsApp message, user prompt, and button "
        "is presented in exact sequence across all participant departments.", st["body"])))
    story.append(sp(8))

    # Roles Summary
    story.append(Paragraph("Department Roles &amp; Operational Responsibilities", st["h2"]))
    key_data = [
        [Paragraph("Role", st["th"]), Paragraph("Person / Department", st["th"]),
         Paragraph("Operational Responsibility", st["th"])],
        [Paragraph("Sales Rep", st["tdb"]), Paragraph("Sales (e.g. Tinashe)", st["td"]),
         Paragraph("Selects operating company, inputs Trip ID, resolves shortfall, registers Customer IDs and expected fees, and tracks driver live location during transit.", st["td"])],
        [Paragraph("Logistics Supervisor", st["tdb"]), Paragraph("Logistics (Edward)", st["td"]),
         Paragraph("Allocates truck plate, driver name, crew count, meal count, and route toll fees. (Cannot see sales totals). Confirms via buttons [Confirm] / [Change].", st["td"])],
        [Paragraph("Executive Approver", st["tdb"]), Paragraph("Management (Zayn)", st["td"]),
         Paragraph("Receives the automated allowance approval ticket. Reviews and approves or recalculates. Approval triggers Accounts money payout.", st["td"])],
        [Paragraph("Accounts Team", st["tdb"]), Paragraph("Accounts Office", st["td"]),
         Paragraph("Receives payout notification upon Zayn's approval and executes cash allocation / transfer to driver.", st["td"])],
        [Paragraph("Driver", st["tdb"]), Paragraph("Fleet Driver (John Banda)", st["td"]),
         Paragraph("Enters departure time, streams live location to Sales Rep, logs customer delivery fees (auto-verified), logs emergency fuel (pump video) &amp; other repairs, toggles return status.", st["td"])],
        [Paragraph("Sales Admin", st["tdb"]), Paragraph("Sales Admin (1 per Company)", st["td"]),
         Paragraph("Conducts physical balancing session upon return for their assigned company; reviews expenses against physical receipts &amp; pump video with automated reconciliation report.", st["td"])],
        [Paragraph("Logistics Manager", st["tdb"]), Paragraph("Logistics Management", st["td"]),
         Paragraph("Adjudicates un-balanced trip discrepancy reports; approves reimbursement fund transfers or allocates deficit to driver pending ledger.", st["td"])],
    ]
    t_key = Table(key_data, colWidths=[1.3*inch, 1.5*inch, 4.2*inch])
    t_key.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#0F172A")),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING", (0,0), (-1,-1), 5), ("RIGHTPADDING", (0,0), (-1,-1), 5),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
    ]))
    story.append(t_key)
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════
    # STAGE 1 — FLEET TRIP APPROVAL & COMPANY ASSIGNMENT
    # ══════════════════════════════════════════════════════════════════
    stage_banner("STAGE 1 — Trip Initiation, Company Selection &amp; Fleet Approval",
                 "Role: Sales Rep  |  Handler: fleet_approval_handler.py",
                 "#166534", story, st)

    story.append(Paragraph(
        "At the start of the trip approval process, the system prompts for the operating company. "
        "There are 3 companies, each with 1 designated Sales Admin. "
        "Selecting the company tags the trip immediately so that the balancing session on return "
        "is routed directly to that company's Sales Admin.", st["body"]))
    story.append(sp(4))

    story.append(Paragraph("1.  Sales Rep opens bot and selects company", st["h3"]))
    story.append(bubble(["Hi"], "Sales Rep", "#15803D", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["TAGONESWA SALES PORTAL",
         "────────────────────",
         "Welcome Tinashe!",
         "Please select an option:"],
        "BOT", "#166534", "#DCF8C6",
        buttons=["Fleet Trip Approval", "My Pending Balance"]))
    story.append(sp())

    story.append(bubble(["Fleet Trip Approval"], "Sales Rep", "#15803D", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["Which company is this trip for?",
         "A. TG Hardware",
         "B. LG Plast",
         "C. Kreckle"],
        "BOT", "#166534", "#DCF8C6",
        buttons=["A. TG Hardware", "B. LG Plast", "C. Kreckle"]))
    story.append(sp())

    story.append(bubble(["A. TG Hardware"], "Sales Rep", "#15803D", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["Company: A. TG Hardware",
         "Assigned Sales Admin: Tagoneswa Hardware Admin",
         "",
         "Please enter your Trip ID from Favlogix:"],
        "BOT", "#166534", "#DCF8C6"))
    story.append(sp(6))

    # Flow A
    story.append(Paragraph("Flow A — Trip Meets Route Threshold (No Shortfall)", st["h2"]))
    story.append(bubble(["TRIP-2026-00123"], "Sales Rep", "#15803D", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["TRIP APPROVED",
         "────────────────────",
         "Company:     A. TG Hardware",
         "Trip:        TRIP-2026-00123",
         "Destination: Bulawayo",
         "Sales Total: $22,500.00",
         "",
         "Trip is cleared for dispatch."],
        "BOT", "#166534", "#DCF8C6",
        buttons=["Authorize Dispatch", "Add Transport", "Main Menu"]))
    story.append(sp())

    story.append(bubble(["Authorize Dispatch"], "Sales Rep", "#15803D", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["Please charge all customers in Favlogix and select YES when done:"],
        "BOT", "#166534", "#DCF8C6",
        buttons=["YES", "NO"]))
    story.append(sp(6))

    # Flow B
    story.append(Paragraph("Flow B — Trip Has Shortfall (Transport Fee Required)", st["h2"]))
    story.append(Paragraph(
        "Internal calculations (route minimums, shortfall gap, 4% formula) are hidden from the Sales Rep. "
        "The bot displays only the Trip ID, Destination, Sales Total, and the transport fee required.", st["note"]))
    story.append(sp(2))

    story.append(bubble(["TRIP-2026-00456"], "Sales Rep", "#15803D", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["FLEET TRIP DETAILS",
         "────────────────────",
         "Company:     A. TG Hardware",
         "Trip:        TRIP-2026-00456",
         "Destination: Gweru",
         "Sales Total: $14,200.00",
         "Transport Fee to Take: $152.00",
         "────────────────────",
         "Please select an option below:"],
        "BOT", "#166534", "#DCF8C6",
        buttons=["Full Charge", "Partial Charge", "Add to Pending"]))
    story.append(sp())

    story.append(Paragraph("Shortfall Option 1 — Full Charge (Direct Execution):", st["h3"]))
    story.append(bubble(["Full Charge"], "Sales Rep", "#15803D", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["FULL TRANSPORT CHARGE SELECTED",
         "Trip: TRIP-2026-00456 | Transport Fee: $152.00",
         "────────────────────",
         "Please charge all customers in Favlogix and select YES when done:"],
        "BOT", "#166534", "#DCF8C6",
        buttons=["YES", "NO"]))
    story.append(sp())

    story.append(Paragraph("Shortfall Option 2 — Partial Charge (Prompts for Amount):", st["h3"]))
    story.append(bubble(["Partial Charge"], "Sales Rep", "#15803D", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(["How much did you charge the customer? (enter amount)"], "BOT", "#166534", "#DCF8C6"))
    story.append(sp())
    story.append(bubble(["100"], "Sales Rep", "#15803D", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["$100.00 recorded as charged.",
         "Remaining $52.00 added to your pending balance.",
         "────────────────────",
         "Please charge all customers in Favlogix and select YES when done:"],
        "BOT", "#166534", "#DCF8C6",
        buttons=["YES", "NO"]))
    story.append(sp())

    story.append(Paragraph("Shortfall Option 3 — Add to Pending (Direct Execution):", st["h3"]))
    story.append(bubble(["Add to Pending"], "Sales Rep", "#15803D", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["Full transport fee of $152.00 added to your pending recovery balance.",
         "────────────────────",
         "Please charge all customers in Favlogix and select YES when done:"],
        "BOT", "#166534", "#DCF8C6",
        buttons=["YES", "NO"]))

    rule(story)
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════
    # STAGE 2 — CONFIRM CHARGES & REGISTER CUSTOMER IDS
    # ══════════════════════════════════════════════════════════════════
    stage_banner("STAGE 2 — Customer Transport Fee Confirmation &amp; Schedule Registration",
                 "Role: Sales Rep  |  Trigger: Automatic post-dispatch",
                 "#1D4ED8", story, st)

    story.append(Paragraph(
        "Before the truck can be assigned, the Sales Rep confirms in Favlogix that all customer "
        "transport fees are added. Upon tapping YES, the Sales Rep registers the Customer IDs "
        "and their expected transport fees, enabling automatic payment verification during transit.", st["body"]))
    story.append(sp(4))

    story.append(bubble(
        ["Have you charged all customers their",
         "transport fee in Favlogix for",
         "Trip TRIP-2026-00456?"],
        "BOT", "#166534", "#DCF8C6",
        buttons=["YES", "NO"]))
    story.append(sp(4))

    story.append(Paragraph("If Sales Rep selects NO:", st["h3"]))
    story.append(bubble(["NO"], "Sales Rep", "#15803D", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["Please charge all customers in Favlogix",
         "and select button YES below when done."],
        "BOT", "#166534", "#DCF8C6",
        buttons=["YES"]))
    story.append(sp(6))

    story.append(Paragraph("If Sales Rep selects YES (Registers Customer ID Schedule):", st["h3"]))
    story.append(bubble(["YES"], "Sales Rep", "#15803D", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["Confirmed!",
         "",
         "Please provide the Customer ID and expected",
         "transport fee for each delivery stop on this trip:",
         "(e.g. CUST-101: 45, CUST-102: 60, CUST-103: 47)"],
        "BOT", "#166534", "#DCF8C6"))
    story.append(sp())

    story.append(bubble(["CUST-101: 45, CUST-102: 60, CUST-103: 47"], "Sales Rep", "#15803D", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["CUSTOMER FEE SCHEDULE SAVED",
         "────────────────────",
         "  CUST-101: $45.00",
         "  CUST-102: $60.00",
         "  CUST-103: $47.00",
         "  Total:    $152.00",
         "",
         "The system will automatically verify driver",
         "collections against these Customer IDs during transit!",
         "",
         "Edward has been notified to assign truck &amp; driver."],
        "BOT", "#166534", "#DCF8C6"))

    rule(story)
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════
    # STAGE 3 — EDWARD ASSIGNS TRUCK & DRIVER (NO SALES AMOUNT VISIBLE)
    # ══════════════════════════════════════════════════════════════════
    stage_banner("STAGE 3 — Truck &amp; Driver Allocation with Route Costing",
                 "Role: Logistics Supervisor (Edward)  |  Handler: logistics_handler.py",
                 "#1D4ED8", story, st)

    story.append(Paragraph(
        "Edward types the truck registration, driver name, crew count, meal count, "
        "number of toll gates and total toll cost. <b>Edward is not able to see the total sales amount</b>. "
        "When the assignment summary is generated, Edward confirms via buttons [Confirm] or [Change].", st["body"]))
    story.append(sp(4))

    story.append(Paragraph("1.  Edward receives allocation alert (No sales value visible)", st["h3"]))
    story.append(bubble(
        ["TRUCK ASSIGNMENT NEEDED",
         "────────────────────",
         "Company: Tagoneswa Hardware",
         "Trip:    TRIP-2026-00456",
         "Route:   Gweru",
         "Rep:     Tinashe",
         "",
         "Please type the truck registration number:"],
        "BOT to Edward", "#1D4ED8", "#DBEAFE"))
    story.append(sp())

    story.append(Paragraph("2.  Edward types truck registration", st["h3"]))
    story.append(bubble(["ZW 123 ABC"], "Edward", "#1D4ED8", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["Truck ZW 123 ABC noted.",
         "",
         "Please type the driver's full name:"],
        "BOT to Edward", "#1D4ED8", "#DBEAFE"))
    story.append(sp())

    story.append(Paragraph("3.  Edward types driver name", st["h3"]))
    story.append(bubble(["John Banda"], "Edward", "#1D4ED8", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["Driver John Banda noted.",
         "",
         "How many crew members on this trip?"],
        "BOT to Edward", "#1D4ED8", "#DBEAFE"))
    story.append(sp())

    story.append(Paragraph("4.  Edward enters crew count", st["h3"]))
    story.append(bubble(["2"], "Edward", "#1D4ED8", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["How many meals for this trip?"],
        "BOT to Edward", "#1D4ED8", "#DBEAFE"))
    story.append(sp())

    story.append(Paragraph("5.  Edward enters meal count", st["h3"]))
    story.append(bubble(["3"], "Edward", "#1D4ED8", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["How many toll gates on this route?"],
        "BOT to Edward", "#1D4ED8", "#DBEAFE"))
    story.append(sp())

    story.append(Paragraph("6.  Edward enters toll gate count", st["h3"]))
    story.append(bubble(["4"], "Edward", "#1D4ED8", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["What is the total toll cost for this route? (enter amount in $)"],
        "BOT to Edward", "#1D4ED8", "#DBEAFE"))
    story.append(sp())

    story.append(Paragraph("7.  Edward enters total toll cost", st["h3"]))
    story.append(bubble(["34.50"], "Edward", "#1D4ED8", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["ASSIGNMENT SUMMARY",
         "────────────────────",
         "Company: Tagoneswa Hardware",
         "Trip:    TRIP-2026-00456  |  Route: Gweru",
         "Truck:   ZW 123 ABC",
         "Driver:  John Banda",
         "Crew:    2 people  |  Meals: 3",
         "Tolls:   4 gates   |  Toll cost: $34.50",
         "",
         "AUTO-CALCULATED ALLOWANCES:",
         "  Toll cost:               $34.50",
         "  Food ($2 x 2 x 3):       $12.00",
         "  ─────────────────────────",
         "  Total allowance:         $46.50",
         "",
         "Please confirm this assignment:"],
        "BOT to Edward", "#1D4ED8", "#DBEAFE",
        buttons=["Confirm", "Change"]))
    story.append(sp())

    story.append(Paragraph("8.  Edward confirms via button [Confirm]", st["h3"]))
    story.append(bubble(["Confirm"], "Edward", "#1D4ED8", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["Assignment saved. Allowance approval",
         "ticket sent to Zayn."],
        "BOT to Edward", "#1D4ED8", "#DBEAFE"))
    story.append(sp(4))

    story.append(bubble(
        ["Truck ZW 123 ABC assigned to your trip.",
         "Driver: John Banda.",
         "Departure pending allowance sign-off."],
        "BOT to Sales Rep", "#166534", "#DCF8C6"))
    story.append(sp(2))
    story.append(bubble(
        ["You have been assigned to Trip TRIP-2026-00456.",
         "Route: Gweru  |  Truck: ZW 123 ABC.",
         "Departure pending allowance approval."],
        "BOT to Driver", "#15803D", "#DCFCE7"))

    rule(story)
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════
    # STAGE 4 — ZAYN APPROVAL & ACCOUNTS MONEY TRANSFER
    # ══════════════════════════════════════════════════════════════════
    stage_banner("STAGE 4 — Zayn Allowance Approval &amp; Accounts Money Transfer",
                 "Role: Zayn &amp; Accounts Team  |  Handler: accounts_handler.py",
                 "#92400E", story, st)

    story.append(Paragraph(
        "<b>Zayn receives the automated approval prompt</b> to review the toll and meal allowances. "
        "When Zayn approves, the bot notifies the Accounts team to execute the money transfer / cash payout to the driver.", st["body"]))
    story.append(sp(4))

    story.append(Paragraph("1.  Zayn receives the approval prompt", st["h3"]))
    story.append(bubble(
        ["ALLOWANCE APPROVAL NEEDED",
         "────────────────────",
         "Company: Tagoneswa Hardware",
         "Trip:    TRIP-2026-00456  |  Route: Gweru",
         "Driver:  John Banda  |  Truck: ZW 123 ABC",
         "Crew:    2 people  |  Meals: 3  |  Tolls: 4",
         "────────────────────",
         "Toll cost:         $34.50",
         "Food ($2 x 2 x 3): $12.00",
         "────────────────────",
         "Total allowance:   $46.50",
         "",
         "Please approve or recalculate:"],
        "BOT to Zayn", "#92400E", "#FEF9C3",
        buttons=["Approve", "Recalculate"]))
    story.append(sp(4))

    story.append(Paragraph("2.  Zayn approves", st["h2"]))
    story.append(bubble(["Approve"], "Zayn", "#92400E", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["$46.50 allowance approved.",
         "Notification dispatched to Accounts to execute money transfer."],
        "BOT to Zayn", "#92400E", "#FEF9C3"))
    story.append(sp())

    story.append(Paragraph("3.  Accounts receives notification to transfer funds to driver", st["h3"]))
    story.append(bubble(
        ["ALLOWANCE APPROVED — TRANSFER REQUIRED",
         "────────────────────",
         "Company:     Tagoneswa Hardware",
         "Trip:        TRIP-2026-00456  |  Route: Gweru",
         "Driver:      John Banda  |  Truck: ZW 123 ABC",
         "Approved by: Zayn",
         "Amount:      $46.50",
         "────────────────────",
         "Please handle cash payout / transfer to Driver John Banda.",
         "Tap button below once transfer is complete:"],
        "BOT to Accounts", "#92400E", "#FEF9C3",
        buttons=["Transfer Done"]))
    story.append(sp())

    story.append(Paragraph("4.  Accounts completes transfer and driver sets departure time", st["h3"]))
    story.append(bubble(["Transfer Done"], "Accounts", "#92400E", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["YOUR ALLOWANCES ARE APPROVED",
         "────────────────────",
         "Trip:   TRIP-2026-00456  |  Route: Gweru",
         "Truck:  ZW 123 ABC",
         "  Toll:   $34.50",
         "  Food:   $12.00",
         "  Total:  $46.50",
         "",
         "Funds have been released by Accounts.",
         "",
         "What time will you depart? (e.g. 07:30)"],
        "BOT to Driver", "#15803D", "#DCFCE7"))
    story.append(sp())

    story.append(bubble(["07:30"], "Driver (John Banda)", "#15803D", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["Departure time set to 07:30.",
         "",
         "Tap the button below when you leave the yard:"],
        "BOT to Driver", "#15803D", "#DCFCE7",
        buttons=["Trip Started"]))

    rule(story)
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════
    # STAGE 5 — LIVE TRANSIT, LOCATION SHARING & EMERGENCY CHARGES
    # ══════════════════════════════════════════════════════════════════
    stage_banner("STAGE 5 — Live Transit, Location Streaming &amp; Emergency Charges",
                 "Role: Driver &amp; Sales Rep  |  Handler: driver_handler.py",
                 "#065F46", story, st)

    story.append(Paragraph(
        "When the driver taps <b>Trip Started</b>, the bot initiates live WhatsApp location streaming to the perspective Sales Rep. "
        "During transit, the driver has 3 options: <b>[Delivery Charges]</b>, <b>[Emergency Charges]</b>, and <b>[I am Returning]</b>.", st["body"]))
    story.append(sp(4))

    story.append(Paragraph("1.  Driver taps Trip Started — Live location sent to Sales Rep", st["h3"]))
    story.append(bubble(["Trip Started"], "Driver (John Banda)", "#15803D", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["Trip TRIP-2026-00456 is now ACTIVE.",
         "Departed: 07:30  |  Route: Gweru",
         "",
         "Live location streaming is ON:",
         "Your location is being shared with Sales Rep Tinashe.",
         "",
         "Use the options below during deliveries:"],
        "BOT to Driver", "#15803D", "#DCFCE7",
        buttons=["Delivery Charges", "Emergency Charges", "I am Returning"]))
    story.append(sp())

    story.append(bubble(
        ["LIVE LOCATION STREAMING ACTIVE — TRIP-2026-00456",
         "Driver John Banda has departed the yard.",
         "Truck: ZW 123 ABC  |  Route: Gweru",
         "Live tracking link: [View Driver Live Location]"],
        "BOT to Sales Rep (Tinashe)", "#166534", "#DCF8C6"))
    story.append(sp(6))

    story.append(Paragraph("2.  Delivery Charges — Automated Customer ID Match", st["h2"]))
    story.append(bubble(["Delivery Charges"], "Driver (John Banda)", "#15803D", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(["Please enter the Customer ID:"], "BOT to Driver", "#15803D", "#DCFCE7"))
    story.append(sp())
    story.append(bubble(["CUST-101"], "Driver (John Banda)", "#15803D", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(["How much transport charge did CUST-101 pay? (enter amount in $)"], "BOT to Driver", "#15803D", "#DCFCE7"))
    story.append(sp())
    story.append(bubble(["45"], "Driver (John Banda)", "#15803D", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["AUTOMATED SYSTEM VERIFICATION",
         "────────────────────",
         "Customer ID:      CUST-101",
         "Expected Fee:     $45.00",
         "Collected Fee:    $45.00",
         "Status:           VERIFIED - MATCHED",
         "",
         "Logged successfully in trip ledger."],
        "BOT to Driver", "#15803D", "#DCFCE7",
        buttons=["Delivery Charges", "Emergency Charges", "I am Returning"]))
    story.append(sp(6))

    story.append(Paragraph("3.  Emergency Charges — [Emergency Fuel] vs [Other]", st["h2"]))
    story.append(bubble(["Emergency Charges"], "Driver (John Banda)", "#15803D", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["EMERGENCY CHARGES",
         "Please select the emergency expense category:"],
        "BOT to Driver", "#15803D", "#DCFCE7",
        buttons=["Emergency Fuel", "Other"]))
    story.append(sp())

    story.append(Paragraph("Branch A: Emergency Fuel (Anti-Fraud Video Required)", st["h3"]))
    story.append(bubble(["Emergency Fuel"], "Driver (John Banda)", "#15803D", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["EMERGENCY FUEL INSTRUCTIONS",
         "────────────────────",
         "Record a continuous video on your phone:",
         "  1. Film pump meter running while fuel is pumped.",
         "  2. State date and time out loud clearly.",
         "Keep this video for the return balancing session.",
         "Do not upload video to the bot.",
         "────────────────────",
         "How much did you take from collections for fuel? (in $)"],
        "BOT to Driver", "#15803D", "#DCFCE7"))
    story.append(sp())
    story.append(bubble(["35"], "Driver (John Banda)", "#15803D", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["$35.00 emergency fuel noted.",
         "Keep pump video ready for return balancing session."],
        "BOT to Driver", "#15803D", "#DCFCE7",
        buttons=["Delivery Charges", "Emergency Charges", "I am Returning"]))
    story.append(sp())

    story.append(Paragraph("Branch B: Other Emergency Expense (Issue Description & Cost)", st["h3"]))
    story.append(bubble(["Other"], "Driver (John Banda)", "#15803D", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(["Please describe the emergency issue or expense:"], "BOT to Driver", "#15803D", "#DCFCE7"))
    story.append(sp())
    story.append(bubble(["Flat tire puncture repair"], "Driver (John Banda)", "#15803D", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(["How much money was spent on this issue? (enter amount in $)"], "BOT to Driver", "#15803D", "#DCFCE7"))
    story.append(sp())
    story.append(bubble(["15"], "Driver (John Banda)", "#15803D", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["$15.00 logged for issue: Flat tire puncture repair.",
         "Retain physical receipt for balancing session."],
        "BOT to Driver", "#15803D", "#DCFCE7",
        buttons=["Delivery Charges", "Emergency Charges", "I am Returning"]))
    story.append(sp(6))

    story.append(Paragraph("4.  Driver taps [I am Returning] — Live location turns OFF", st["h2"]))
    story.append(bubble(["I am Returning"], "Driver (John Banda)", "#15803D", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["Live location tracking turned OFF.",
         "Sales Rep Tinashe has been notified that you are",
         "returning to base.",
         "",
         "Use the options below on your return journey:"],
        "BOT to Driver", "#15803D", "#DCFCE7",
        buttons=["Emergency Charges", "I Have Returned"]))
    story.append(sp())

    story.append(bubble(
        ["LIVE TRACKING ENDED — TRIP-2026-00456",
         "Driver John Banda has completed deliveries and is returning to base."],
        "BOT to Sales Rep (Tinashe)", "#166534", "#DCF8C6"))

    rule(story)
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════
    # STAGE 6 — DRIVER RETURNS & BALANCING SESSION
    # ══════════════════════════════════════════════════════════════════
    stage_banner("STAGE 6 — Driver Return &amp; Sales Admin Balancing Session",
                 "Role: Sales Admin (1 per Company)  |  Handler: sales_admin_handler.py",
                 "#5B21B6", story, st)

    story.append(Paragraph(
        "When the driver arrives at base and taps <b>[I Have Returned]</b>, the bot alerts the assigned "
        "Sales Admin (Tagoneswa Hardware). A physical balancing session is held to review Customer ID "
        "collection logs, emergency receipts, and pump video evidence.", st["body"]))
    story.append(sp(4))

    story.append(Paragraph("1.  Driver confirms arrival at base", st["h3"]))
    story.append(bubble(["I Have Returned"], "Driver (John Banda)", "#15803D", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["Arrival confirmed for Trip TRIP-2026-00456.",
         "Company: Tagoneswa Hardware",
         "",
         "Tagoneswa Hardware Sales Admin has been",
         "notified to begin the balancing session."],
        "BOT to Driver", "#15803D", "#DCFCE7"))
    story.append(sp())

    story.append(Paragraph("2.  Tagoneswa Hardware Sales Admin receives balancing ticket", st["h3"]))
    story.append(bubble(
        ["DRIVER HAS RETURNED — TRIP-2026-00456",
         "────────────────────",
         "Company:          Tagoneswa Hardware",
         "Driver:           John Banda  |  Route: Gweru",
         "Truck:            ZW 123 ABC",
         "Allowances Given: $46.50",
         "Emergency Fuel:   $35.00 (verify pump video)",
         "Emergency Other:  $15.00 (Tire puncture repair)",
         "────────────────────",
         "AUTOMATED CUSTOMER ID AUDIT:",
         "  CUST-101: $45.00 / $45.00 (MATCHED)",
         "  CUST-102: $60.00 / $60.00 (MATCHED)",
         "  CUST-103: $47.00 / $47.00 (MATCHED)",
         "  Total Collected: $152.00 / $152.00",
         "",
         "Please conduct physical balancing session.",
         "Compare receipts &amp; pump video against ledger:"],
        "BOT to Sales Admin (Tagoneswa Hardware)", "#5B21B6", "#F3E8FF",
        buttons=["Balanced", "Not Balancing"]))
    story.append(sp(6))

    story.append(Paragraph("Option A — Trip balances perfectly", st["h2"]))
    story.append(bubble(["Balanced"], "Sales Admin", "#5B21B6", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["Balancing confirmed. Trip TRIP-2026-00456",
         "is CLOSED. Broadcast summary issued."],
        "BOT to Sales Admin", "#5B21B6", "#F3E8FF"))
    story.append(sp(6))

    story.append(Paragraph("Option B — Deficit or variance detected", st["h2"]))
    story.append(bubble(["Not Balancing"], "Sales Admin", "#5B21B6", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(["Enter discrepancy variance amount: (in $)"], "BOT to Sales Admin", "#5B21B6", "#F3E8FF"))
    story.append(sp())
    story.append(bubble(["12.50"], "Sales Admin", "#5B21B6", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(["Enter discrepancy reason and audit notes:"], "BOT to Sales Admin", "#5B21B6", "#F3E8FF"))
    story.append(sp())
    story.append(bubble(["Pump video showed $47.50 but driver reported $35.00 on bot"], "Sales Admin", "#5B21B6", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["Discrepancy of $12.50 recorded.",
         "Escalated to Logistics Manager for final adjudication."],
        "BOT to Sales Admin", "#5B21B6", "#F3E8FF"))

    rule(story)
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════
    # STAGE 7 — REIMBURSEMENT & TRIP CLOSED
    # ══════════════════════════════════════════════════════════════════
    stage_banner("STAGE 7 — Manager Adjudication &amp; Final Trip Closure",
                 "Role: Logistics Manager  |  Handler: logistics_manager_handler.py",
                 "#9A3412", story, st)

    story.append(Paragraph(
        "If an audit discrepancy is registered, the Logistics Manager adjudicates. "
        "Approve authorizes an internal fund transfer from Accounts to the Sales Admin. "
        "Reject assigns the balance directly to the driver's pending recovery ledger. "
        "Both branches result in complete trip closure and executive broadcasting.", st["body"]))
    story.append(sp(4))

    story.append(Paragraph("1.  Logistics Manager receives adjudication ticket", st["h3"]))
    story.append(bubble(
        ["REIMBURSEMENT REQUEST — TRIP-2026-00456",
         "────────────────────",
         "Company:     Tagoneswa Hardware",
         "Driver:      John Banda  |  Route: Gweru",
         "Discrepancy: $12.50",
         "Audit Note:  Pump video showed $47.50 but",
         "             driver reported $35.00 on bot",
         "",
         "Please select adjudication outcome:"],
        "BOT to Logistics Manager", "#9A3412", "#FFEDD5",
        buttons=["Approve", "Reject"]))
    story.append(sp(6))

    story.append(Paragraph("Adjudication Branch A — Approved (Reimbursement Dispatched)", st["h2"]))
    story.append(bubble(["Approve"], "Logistics Manager", "#9A3412", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["Approved. Accounts instructed to transfer",
         "$12.50 to Sales Admin.",
         "Trip TRIP-2026-00456 is marked CLOSED."],
        "BOT to Logistics Manager", "#9A3412", "#FFEDD5"))
    story.append(sp())
    story.append(bubble(
        ["TRANSFER REQUIRED",
         "Transfer $12.50 to Sales Admin.",
         "Ref: Approved reimbursement for TRIP-2026-00456."],
        "BOT to Accounts", "#92400E", "#FEF9C3"))
    story.append(sp(6))

    story.append(Paragraph("Adjudication Branch B — Rejected (Assigned to Driver Pending)", st["h2"]))
    story.append(bubble(["Reject"], "Logistics Manager", "#9A3412", "#FFFFFF"))
    story.append(sp())
    story.append(bubble(
        ["Rejected. $12.50 added to John Banda's",
         "driver pending balance.",
         "Trip TRIP-2026-00456 is marked CLOSED."],
        "BOT to Logistics Manager", "#9A3412", "#FFEDD5"))
    story.append(sp())
    story.append(bubble(
        ["$12.50 added to your pending recovery ledger",
         "for Trip TRIP-2026-00456.",
         "Reason: Audit discrepancy rejected by manager."],
        "BOT to Driver", "#15803D", "#DCFCE7"))
    story.append(sp(6))

    # Broadcast
    story.append(Paragraph("TRIP CLOSED — Stakeholder Broadcasts (Confidentiality Enforced)", st["h2"]))
    story.append(Paragraph(
        "Upon closure, the system dispatches final closing summaries. "
        "<b>Critical Confidentiality Constraint:</b> Sales Total is strictly concealed from operational staff "
        "(Driver, Sales Rep, Sales Admin, and Edward) and provided exclusively to Executive Management (Zayn & Accounts).", st["body"]))
    story.append(sp(3))

    # Operational summary (Sales Total Strictly Hidden)
    closed_lines_operational = [
        "TRIP CLOSED — TRIP-2026-00456",
        "────────────────────",
        "Company: A. TG Hardware",
        "Route:   Gweru  |  Truck: ZW 123 ABC",
        "Driver:  John Banda  |  Crew: 2 people",
        "────────────────────",
        "Allowances Given: $46.50",
        "Emergency Fuel:   $35.00",
        "Deliveries:       3 stops logged",
        "────────────────────",
        "Final Status:     CLOSED",
        f"Closed At:        {datetime.datetime.now().strftime('%d %b %Y  %I:%M %p')}",
    ]

    # Executive summary (Includes Sales Total)
    closed_lines_executive = [
        "TRIP CLOSED (EXECUTIVE) — TRIP-2026-00456",
        "────────────────────",
        "Company: A. TG Hardware",
        "Route:   Gweru  |  Truck: ZW 123 ABC",
        "Driver:  John Banda  |  Crew: 2 people",
        "────────────────────",
        "Sales Total:      $14,200.00",
        "Allowances Given: $46.50",
        "Emergency Fuel:   $35.00",
        "Deliveries:       3 stops logged",
        "────────────────────",
        "Final Status:     CLOSED",
        f"Closed At:        {datetime.datetime.now().strftime('%d %b %Y  %I:%M %p')}",
    ]

    story.append(Paragraph("<b>1. Operational Staff Copies (Sales Total STRICTLY HIDDEN):</b>", st["h3"]))
    for lbl, lclr, bg in [
        ("BOT to Sales Rep",    "#166534", "#DCF8C6"),
        ("BOT to Edward",       "#1D4ED8", "#DBEAFE"),
        ("BOT to Driver",       "#15803D", "#DCFCE7"),
        ("BOT to Sales Admin",  "#5B21B6", "#F3E8FF"),
    ]:
        story.append(bubble(closed_lines_operational, lbl, lclr, bg))
        story.append(sp(2))

    story.append(sp(4))
    story.append(Paragraph("<b>2. Executive Management Copy (Includes Sales Total):</b>", st["h3"]))
    for lbl, lclr, bg in [
        ("BOT to Zayn (Executive)",     "#92400E", "#FEF9C3"),
        ("BOT to Accounts Office",      "#92400E", "#FEF9C3"),
    ]:
        story.append(bubble(closed_lines_executive, lbl, lclr, bg))
        story.append(sp(2))

    rule(story)
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════
    # BUTTON REFERENCE
    # ══════════════════════════════════════════════════════════════════
    story.append(Paragraph("Master Interactive Button Reference", st["h1"]))
    story.append(Paragraph(
        "Comprehensive directory of all interactive buttons in the Sales and Fleet ecosystem. "
        "Strict standard: zero emoji prefixes, concise text, automated system validations.", st["body"]))
    story.append(sp(6))

    btn_rows = [
        [Paragraph("Button Text", st["th"]),
         Paragraph("Target Role", st["th"]),
         Paragraph("Stage", st["th"]),
         Paragraph("Automated System Action", st["th"])],
        # Stage 1
        [Paragraph("Fleet Trip Approval", st["tdb"]), Paragraph("Sales Rep", st["td"]),
         Paragraph("1", st["td"]), Paragraph("Prompts user to select operating company.", st["td"])],
        [Paragraph("My Pending Balance", st["tdb"]), Paragraph("Sales Rep", st["td"]),
         Paragraph("1", st["td"]), Paragraph("Queries and outputs current outstanding recovery balance.", st["td"])],
        [Paragraph("A. TG Hardware", st["tdb"]), Paragraph("Sales Rep", st["td"]),
         Paragraph("1", st["td"]), Paragraph("Assigns trip to TG Hardware and its Sales Admin.", st["td"])],
        [Paragraph("B. LG Plast", st["tdb"]), Paragraph("Sales Rep", st["td"]),
         Paragraph("1", st["td"]), Paragraph("Assigns trip to LG Plast and its Sales Admin.", st["td"])],
        [Paragraph("C. Kreckle", st["tdb"]), Paragraph("Sales Rep", st["td"]),
         Paragraph("1", st["td"]), Paragraph("Assigns trip to Kreckle and its Sales Admin.", st["td"])],
        [Paragraph("Authorize Dispatch", st["tdb"]), Paragraph("Sales Rep", st["td"]),
         Paragraph("1", st["td"]), Paragraph("Advances trip to Favlogix charge check.", st["td"])],
        [Paragraph("Add Transport", st["tdb"]), Paragraph("Sales Rep", st["td"]),
         Paragraph("1", st["td"]), Paragraph("Allows rep to add transport charge to reduce pending balance.", st["td"])],
        [Paragraph("Full Charge", st["tdb"]), Paragraph("Sales Rep", st["td"]),
         Paragraph("1 (shortfall)", st["td"]), Paragraph("Instantly records full fee payment without prompting for amount.", st["td"])],
        [Paragraph("Partial Charge", st["tdb"]), Paragraph("Sales Rep", st["td"]),
         Paragraph("1 (shortfall)", st["td"]), Paragraph("Prompts for amount charged; transfers remainder to pending balance.", st["td"])],
        [Paragraph("Add to Pending", st["tdb"]), Paragraph("Sales Rep", st["td"]),
         Paragraph("1 (shortfall)", st["td"]), Paragraph("Instantly posts full transport fee to pending balance without prompting.", st["td"])],
        # Stage 2
        [Paragraph("YES", st["tdb"]), Paragraph("Sales Rep", st["td"]),
         Paragraph("2", st["td"]), Paragraph("Confirms all charges in Favlogix; opens customer manifest entry.", st["td"])],
        [Paragraph("NO", st["tdb"]), Paragraph("Sales Rep", st["td"]),
         Paragraph("2", st["td"]), Paragraph("Holds workflow; repeats verification until charges are added.", st["td"])],
        # Stage 3
        [Paragraph("Allocate Trip", st["tdb"]), Paragraph("Edward", st["td"]),
         Paragraph("3", st["td"]), Paragraph("Begins allocation for next queued trip.", st["td"])],
        [Paragraph("Trip Queue", st["tdb"]), Paragraph("Edward", st["td"]),
         Paragraph("3", st["td"]), Paragraph("Displays list of pending trips awaiting truck allocation.", st["td"])],
        [Paragraph("Confirm", st["tdb"]), Paragraph("Edward", st["td"]),
         Paragraph("3", st["td"]), Paragraph("Confirms truck and driver assignment; triggers allowance ticket to Zayn.", st["td"])],
        [Paragraph("Change", st["tdb"]), Paragraph("Edward", st["td"]),
         Paragraph("3", st["td"]), Paragraph("Restarts assignment flow to re-enter truck plate or driver details.", st["td"])],
        # Stage 4
        [Paragraph("Approve", st["tdb"]), Paragraph("Zayn", st["td"]),
         Paragraph("4", st["td"]), Paragraph("Approves calculated allowance; dispatches transfer ticket to Accounts.", st["td"])],
        [Paragraph("Recalculate", st["tdb"]), Paragraph("Zayn", st["td"]),
         Paragraph("4", st["td"]), Paragraph("Opens manual crew/meal adjustments; updates total allowance.", st["td"])],
        [Paragraph("Transfer Done", st["tdb"]), Paragraph("Accounts", st["td"]),
         Paragraph("4", st["td"]), Paragraph("Confirms cash allocation / transfer released; prompts driver for departure time.", st["td"])],
        # Stage 5
        [Paragraph("Trip Started", st["tdb"]), Paragraph("Driver", st["td"]),
         Paragraph("5", st["td"]), Paragraph("Activates trip; initiates live location streaming to Sales Rep.", st["td"])],
        [Paragraph("Delivery Charges", st["tdb"]), Paragraph("Driver", st["td"]),
         Paragraph("5", st["td"]), Paragraph("Prompts for Customer ID; verifies automatically against schedule.", st["td"])],
        [Paragraph("Cash", st["tdb"]), Paragraph("Driver", st["td"]),
         Paragraph("5", st["td"]), Paragraph("Records cash payment from customer.", st["td"])],
        [Paragraph("Bank/EcoCash", st["tdb"]), Paragraph("Driver", st["td"]),
         Paragraph("5", st["td"]), Paragraph("Records electronic/bank payment from customer.", st["td"])],
        [Paragraph("Unpaid", st["tdb"]), Paragraph("Driver", st["td"]),
         Paragraph("5", st["td"]), Paragraph("Flags customer order as unpaid for follow-up.", st["td"])],
        [Paragraph("Emergency Charges", st["tdb"]), Paragraph("Driver", st["td"]),
         Paragraph("5", st["td"]), Paragraph("Opens emergency sub-menu options [Emergency Fuel] and [Other].", st["td"])],
        [Paragraph("Emergency Fuel", st["tdb"]), Paragraph("Driver", st["td"]),
         Paragraph("5", st["td"]), Paragraph("Prompts video pump audit instructions; records fuel dollar amount.", st["td"])],
        [Paragraph("Other", st["tdb"]), Paragraph("Driver", st["td"]),
         Paragraph("5", st["td"]), Paragraph("Prompts driver to type issue description and dollar amount spent.", st["td"])],
        [Paragraph("I am Returning", st["tdb"]), Paragraph("Driver", st["td"]),
         Paragraph("5", st["td"]), Paragraph("Turns OFF live location; alerts Sales Rep; displays return buttons.", st["td"])],
        [Paragraph("I Have Returned", st["tdb"]), Paragraph("Driver", st["td"]),
         Paragraph("5", st["td"]), Paragraph("Confirms arrival at base; summons assigned company Sales Admin for balancing.", st["td"])],
        # Stage 6
        [Paragraph("Balanced", st["tdb"]), Paragraph("Sales Admin", st["td"]),
         Paragraph("6", st["td"]), Paragraph("Validates physical receipts &amp; pump video; marks trip CLOSED.", st["td"])],
        [Paragraph("Not Balancing", st["tdb"]), Paragraph("Sales Admin", st["td"]),
         Paragraph("6", st["td"]), Paragraph("Logs deficit and audit notes; forwards ticket to Logistics Manager.", st["td"])],
        # Stage 7
        [Paragraph("Close Trip", st["tdb"]), Paragraph("Logistics Manager", st["td"]),
         Paragraph("7", st["td"]), Paragraph("Closes trip directly when balancing verified.", st["td"])],
        [Paragraph("Approve", st["tdb"]), Paragraph("Logistics Manager", st["td"]),
         Paragraph("7", st["td"]), Paragraph("Orders fund transfer from Accounts to Sales Admin; closes trip.", st["td"])],
        [Paragraph("Reject", st["tdb"]), Paragraph("Logistics Manager", st["td"]),
         Paragraph("7", st["td"]), Paragraph("Charges unapproved variance to driver pending ledger; closes trip.", st["td"])],
    ]

    t_btn = Table(btn_rows, colWidths=[1.6*inch, 1.2*inch, 0.7*inch, 3.5*inch])
    t_btn.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#0F172A")),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("TOPPADDING", (0,0), (-1,-1), 3.5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3.5),
        ("LEFTPADDING", (0,0), (-1,-1), 5),
        ("RIGHTPADDING", (0,0), (-1,-1), 5),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
    ]))
    story.append(t_btn)

    # ──────────────────────────────────────────────────────────────────
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"[OK] PDF saved: {filename}")
    return filename


if __name__ == "__main__":
    build_pdf()
