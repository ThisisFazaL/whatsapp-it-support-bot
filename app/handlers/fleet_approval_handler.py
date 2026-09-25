import logging
import re
from typing import Optional, Dict, Any
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import (
    Employee, Department, ConversationState, FleetTripApproval,
    FleetPendingLedger, FleetTripRequest, get_sales_rep_pending_balance,
    get_sales_rep_ledger_entries, record_pending_ledger_entry,
    create_or_update_fleet_trip_request, save_customer_schedules_batch
)
from app.state_manager import set_user_state, clear_user_state, get_user_state
from app.meta_api import meta_api
from app.services.trip_verification_service import trip_verification_service

logger = logging.getLogger("fleet_approval_handler")

GLOBAL_RESET_KEYWORDS = {
    "hi", "hello", "hey", "menu", "reset", "cancel", "start",
    "exit", "back", "restart", "home", "sales", "portal"
}

# In-memory role override cache for instant WhatsApp one-word role toggling
# Allows +919265368695 to switch live between "SALES" and "MASTER_ADMIN" via chat
SESSION_ROLE_OVERRIDES: Dict[str, str] = {}
SOLO_TEST_OVERRIDE: Optional[bool] = None


def get_solo_test_mode() -> bool:
    global SOLO_TEST_OVERRIDE
    if SOLO_TEST_OVERRIDE is not None:
        return SOLO_TEST_OVERRIDE
    return getattr(settings, "solo_test_mode", True)


def set_solo_test_mode(enabled: bool):
    global SOLO_TEST_OVERRIDE
    SOLO_TEST_OVERRIDE = enabled



def is_valid_phone(phone_str: Optional[str]) -> bool:
    """Returns True if phone_str contains a valid international E.164 phone format (digits only)."""
    if not phone_str:
        return False
    cleaned = phone_str.replace("+", "").strip()
    return bool(cleaned.isdigit() and 7 <= len(cleaned) <= 15)


async def notify_fleet_admin(message: str):
    """
    Sends WhatsApp notification to Fleet Admin Sujit (+263 71 835 2518) and master group.
    """
    admin_phone = getattr(settings, "fleet_admin_phone", "263718352518").replace("+", "").strip()
    if is_valid_phone(admin_phone):
        try:
            await meta_api.send_text_message(admin_phone, message)
            logger.info(f"Fleet action alert delivered to Sujit (+{admin_phone})")
        except Exception as e:
            logger.warning(f"Could not send fleet action alert to Sujit (+{admin_phone}): {e}")

    if is_valid_phone(settings.master_group_phone):
        try:
            await meta_api.send_text_message(settings.master_group_phone, message)
        except Exception as e:
            logger.warning(f"Could not alert master group: {e}")



def get_effective_tester_role(phone: str) -> str:
    """Returns the effective testing role for a given phone (e.g. 'SALES' or 'MASTER_ADMIN')."""
    clean_phone = phone.replace("+", "").strip() if phone else ""
    master_phone = settings.master_admin_phone.replace("+", "").strip()

    if clean_phone == master_phone:
        if clean_phone in SESSION_ROLE_OVERRIDES:
            return SESSION_ROLE_OVERRIDES[clean_phone].upper()
        return getattr(settings, "test_user_role", "SALES").upper()

    return "STANDARD"


async def is_salesperson(session: AsyncSession, phone: str, employee: Optional[Employee] = None) -> bool:
    """
    Determines if user is an authorized Salesperson.
    Returns True if:
    1. Phone is Master Admin and effective testing role is 'SALES'.
    2. Employee's department contains 'sales' (e.g. Sales, Tg Sales, Lg Sales, Sales & Marketing).
    """
    clean_phone = phone.replace("+", "").strip() if phone else ""
    master_phone = settings.master_admin_phone.replace("+", "").strip()

    # Master Admin testing override
    if clean_phone == master_phone:
        role = get_effective_tester_role(clean_phone)
        return role == "SALES"

    # Check employee record
    if not employee and clean_phone:
        emp_res = await session.execute(
            select(Employee).options(selectinload(Employee.department)).where(Employee.phone == clean_phone)
        )
        employee = emp_res.scalars().first()

    if employee:
        # Check loaded department
        dept_name = employee.department.department_name if employee.department else ""
        if not dept_name and employee.department_id:
            dept_obj = await session.get(Department, employee.department_id)
            dept_name = dept_obj.department_name if dept_obj else ""

        if "sales" in dept_name.lower():
            return True

    return False


async def handle_role_switch_command(session: AsyncSession, phone: str, message_text: str) -> bool:
    """
    Enables Master Admin (+919265368695) to switch roles in ONE WORD via WhatsApp.
    Commands:
      'role sales' -> Switches to SALES testing role (2-button menu active)
      'role admin' / 'role master' -> Switches back to full MASTER_ADMIN portal
    """
    clean_phone = phone.replace("+", "").strip() if phone else ""
    master_phone = settings.master_admin_phone.replace("+", "").strip()

    if clean_phone != master_phone:
        return False

    cmd = message_text.strip().lower()
    if cmd in {"mode solo", "test solo", "solo mode", "solo on", "sandbox"}:
        set_solo_test_mode(True)
        SESSION_ROLE_OVERRIDES[clean_phone] = "SALES"
        await clear_user_state(session, clean_phone)
        notice = (
            "🎭 *1-PERSON SOLO TEST SANDBOX ACTIVE* 🟢\n"
            "────────────────────\n"
            "You can now test the **entire A-Z 7-stage workflow** completely alone from this phone number!\n\n"
            "📱 *How it works:*\n"
            "• You play **every role sequentially** directly in this WhatsApp chat!\n"
            "• Stage 1: Sales Rep (Submit trip)\n"
            "• Stage 3: Edward (Allocate vehicle & driver)\n"
            "• Stage 4: Zayn (Approve allowance) & Accounts (Confirm payout)\n"
            "• Stage 5: Driver (Departure, live transit, customer payment, fuel video)\n"
            "• Stage 6: Sales Admin (Physical balancing)\n"
            "• Stage 7: Logistics Manager (Adjudication & closed broadcast)\n\n"
            "🚫 *Real staff are NOT messaged* — all alerts come directly to you.\n\n"
            "💡 To exit solo mode anytime, reply `mode live`.\n"
            "👉 Please select an option below to start:"
        )
        await meta_api.send_text_message(clean_phone, notice)
        emp_res = await session.execute(select(Employee).where(Employee.phone == clean_phone))
        emp = emp_res.scalars().first()
        await send_sales_portal_menu(session, clean_phone, emp)
        return True

    elif cmd in {"mode live", "test live", "live mode", "solo off"}:
        set_solo_test_mode(False)
        notice = (
            "🏢 *LIVE PRODUCTION MODE RESTORED* 🔴\n"
            "────────────────────\n"
            "Notifications will now route to real staff numbers:\n"
            f"• Edward: `+{settings.edward_phone}`\n"
            f"• Zayn: `+{settings.zayn_phone}`\n"
            f"• Fleet Admin: `+{settings.fleet_admin_phone}`\n\n"
            "💡 Reply `mode solo` anytime to return to 1-person sandbox testing."
        )
        await meta_api.send_text_message(clean_phone, notice)
        return True

    elif cmd in {"role sales", "switch sales", "mode sales", "test sales"}:
        SESSION_ROLE_OVERRIDES[clean_phone] = "SALES"
        await clear_user_state(session, clean_phone)
        notice = (
            "🔄 *ROLE SWITCHED TO SALES (TESTING MODE)*\n"
            "────────────────────\n"
            "Your number `+919265368695` is now active as a **Salesperson**.\n\n"
            "When you message the bot, you will receive 3 options:\n"
            "• *[ 💻 IT Support ]*\n"
            "• *[ 🚛 Fleet Approval ]*\n"
            "• *[ ⚖️ Pending Balance ]*\n\n"
            "💡 To revert back to Master Admin at any time, simply reply:\n"
            "👉 `role admin` or `role master`"
        )
        await meta_api.send_text_message(clean_phone, notice)
        # Send the sales menu immediately
        emp_res = await session.execute(select(Employee).where(Employee.phone == clean_phone))
        emp = emp_res.scalars().first()
        await send_sales_portal_menu(session, clean_phone, emp)
        return True

    elif cmd in {"role admin", "role master", "switch admin", "mode admin", "role master_admin", "master"}:
        SESSION_ROLE_OVERRIDES[clean_phone] = "MASTER_ADMIN"
        await clear_user_state(session, clean_phone)
        notice = (
            "👑 *ROLE RESTORED TO MASTER ADMIN*\n"
            "────────────────────\n"
            "Welcome back, *Fazal Saiyed*!\n"
            "Full Master Support Admin dashboard access across IT Support, Projects, and Fleet/Workshop is restored.\n\n"
            "💡 Reply `Hi` anytime to access your Master Admin Portal."
        )
        await meta_api.send_text_message(clean_phone, notice)
        from app.handlers.admin_handler import handle_admin_command
        await handle_admin_command(session, clean_phone, "menu")
        return True

    return False


async def send_sales_portal_menu(session: AsyncSession, phone: str, employee: Optional[Employee] = None):
    """
    Presents the salesperson portal menu:
    1. [ 🚛 Fleet Approval ]
    2. [ ⚖️ Pending Balance ]
    3. [ 💻 IT Support ]
    """
    name = employee.full_name if employee else "Sales Colleague"
    header = "🏢 TAGONESWA SALES & FLEET"
    body = (
        f"👋 Hello *{name}*!\n\n"
        f"Welcome to the Tagoneswa Fleet Portal.\n\n"
        f"Please select an option:\n"
        f"1️⃣ *Fleet Trip Approval* (Verify Trip & Transport Charges)\n"
        f"2️⃣ *Pending Balance Recovery* (Track & Recover Balance)\n"
        f"3️⃣ *IT Support Ticket*\n\n"
        f"💡 _Tap a button below or reply with number 1 - 3:_"
    )
    footer = "Tap a button below to proceed"
    buttons = [
        {"id": "btn_domain_fleet", "title": "🚛 Fleet Approval"},
        {"id": "btn_sales_pending_menu", "title": "⚖️ Pending Balance"},
        {"id": "btn_domain_it", "title": "💻 IT Support"}
    ]
    await set_user_state(session, phone, "select_service", {}, flow_name="sales_portal")
    await meta_api.send_button_message(
        to_phone=phone,
        body_text=body,
        buttons=buttons,
        header_text=header,
        footer_text=footer
    )


async def send_pending_balance_menu(session: AsyncSession, phone: str, employee: Optional[Employee] = None):
    """
    Presents the Tagoneswa Sales Pending Recovery menu:
    1. [ 📊 My Pending Total ]
    2. [ 💵 Record Recovery ]
    """
    header = "⚖️ SALES PENDING RECOVERY"
    body = (
        "⚖️ *PENDING BALANCE MANAGEMENT*\n"
        "────────────────────\n"
        "Track outstanding transport charges to recover, or record surplus amounts recovered from other trips.\n\n"
        "Please select an option below:"
    )
    footer = "Tap a button below to proceed"
    buttons = [
        {"id": "btn_pending_check_balance", "title": "📊 My Pending Total"},
        {"id": "btn_pending_record_recovery", "title": "💵 Record Recovery"}
    ]
    await set_user_state(session, phone, "select_pending_action", {}, flow_name="fleet_pending")
    await meta_api.send_button_message(
        to_phone=phone,
        body_text=body,
        buttons=buttons,
        header_text=header,
        footer_text=footer
    )


async def handle_check_pending_balance(session: AsyncSession, phone: str, employee: Optional[Employee] = None):
    """Shows sales rep their net pending balance to recover and contributing trips."""
    name = employee.full_name if employee else "Sales Colleague"
    clean_phone = phone.replace("+", "").strip()
    total_pending = await get_sales_rep_pending_balance(session, clean_phone)
    entries = await get_sales_rep_ledger_entries(session, clean_phone, limit=5)

    if not entries and total_pending <= 0.0:
        msg = (
            f"📊 *SALES REP PENDING BALANCE*\n"
            f"────────────────────\n"
            f"👤 *Sales Rep:* {name}\n"
            f"📱 *Phone:* `+{clean_phone}`\n"
            f"⚖️ *Total Outstanding to Recover:* *$0.00*\n"
            f"────────────────────\n"
            f"✅ You have no pending transport balance to recover! All orders are clear."
        )
        buttons = [
            {"id": "btn_domain_fleet", "title": "🚛 Fleet Approval"},
            {"id": "btn_sales_menu", "title": "↩️ Main Menu"}
        ]
    else:
        history_lines = []
        for e in entries:
            sign = "+" if e.amount > 0 else "-"
            amt_str = f"{sign}${abs(e.amount):,.2f}"
            t_id = e.trip_id or "General"
            label = "Pending deficit" if e.amount > 0 else "Surplus recovered"
            dt_str = e.created_at.strftime("%d/%m") if e.created_at else ""
            history_lines.append(f"• `{t_id}`: *{amt_str}* ({label}{f' - {dt_str}' if dt_str else ''})")

        history_text = "\n".join(history_lines) if history_lines else "No recent transactions recorded."

        msg = (
            f"📊 *SALES REP PENDING BALANCE*\n"
            f"────────────────────\n"
            f"👤 *Sales Rep:* {name}\n"
            f"📱 *Phone:* `+{clean_phone}`\n"
            f"⚖️ *Total Outstanding to Recover:* *${total_pending:,.2f}*\n"
            f"────────────────────\n"
            f"📋 *Recent Activity:*\n"
            f"{history_text}\n\n"
            f"💡 _When you achieve surplus on high-value trips, tap 'Record Recovery' to deduct from your pending balance._"
        )
        buttons = [
            {"id": "btn_pending_record_recovery", "title": "💵 Record Recovery"},
            {"id": "btn_sales_menu", "title": "↩️ Main Menu"}
        ]

    await clear_user_state(session, clean_phone)
    await meta_api.send_button_message(
        to_phone=clean_phone,
        body_text=msg,
        buttons=buttons,
        header_text="📊 PENDING BALANCE REPORT"
    )


async def get_existing_trip_approval(session: AsyncSession, trip_id: str) -> Optional[FleetTripApproval]:
    """
    Looks up existing Trip Approval record from database.
    Matches exact, TRIP- prefixed, or normalized trip IDs.
    """
    clean_id = trip_id.upper().replace("TRIP-", "").strip()
    if not clean_id:
        return None
    stmt = (
        select(FleetTripApproval)
        .where(
            or_(
                func.upper(FleetTripApproval.trip_id) == clean_id,
                func.upper(FleetTripApproval.trip_id) == f"TRIP-{clean_id}",
                func.replace(func.upper(FleetTripApproval.trip_id), "TRIP-", "") == clean_id
            )
        )
        .order_by(FleetTripApproval.id.desc())
    )
    res = await session.execute(stmt)
    return res.scalars().first()


async def handle_existing_trip_response(
    session: AsyncSession,
    phone: str,
    employee: Optional[Employee],
    existing: FleetTripApproval
) -> bool:
    """
    Handles WhatsApp response when a Trip ID was already entered in the database.
    - If already approved/dispatched: Displays approved status, resolution, and blocks re-entry.
    - If not approved (shortfall pending):
        - If submitted by same user: Allows selecting a shortfall resolution option.
        - If submitted by another user: Shows not approved status and blocks duplicate entry.
    """
    clean_phone = phone.replace("+", "").strip()
    existing_phone = existing.salesperson_phone.replace("+", "").strip() if existing.salesperson_phone else ""
    is_same_user = (clean_phone == existing_phone)
    formatted_date = existing.created_at.strftime("%d %b %Y, %H:%M") if existing.created_at else "Recently"
    sales_name = existing.salesperson_name or "Sales Colleague"

    is_dispatched = (
        existing.status in {
            "DISPATCHED",
            "DISPATCHED_FULL_CHARGE",
            "DISPATCHED_PARTIAL_CHARGE",
            "DISPATCHED_FULL_PENDING",
            "DISPATCHED_WITH_TRANSPORT_CHARGE",
        }
        or existing.dispatch_option in {
            "APPROVED_THRESHOLD",
            "APPROVED_WITH_TRANSPORT_RECOVERY",
            "FULL_CHARGE_PAID",
            "PARTIAL_CHARGE",
            "FULL_TO_PENDING"
        }
    )

    if is_dispatched:
        await clear_user_state(session, phone)
        if existing.dispatch_option == "APPROVED_THRESHOLD" or existing.status in {"APPROVED_MEETS_MINIMUM", "DISPATCHED"}:
            res_summary = "• Resolution: ✅ *Passed Minimum Sales Threshold* (No Transport Charge)"
        elif existing.dispatch_option == "APPROVED_WITH_TRANSPORT_RECOVERY" or existing.status == "DISPATCHED_WITH_TRANSPORT_CHARGE":
            res_summary = (
                f"• Resolution: ✅ *Passed Minimum with Transport Charge Added*\n"
                f"• Transport Paid/Deducted from Pending: ${existing.amount_charged_to_customer:,.2f}"
            )
        elif existing.dispatch_option == "FULL_CHARGE_PAID" or existing.status == "DISPATCHED_FULL_CHARGE":
            res_summary = f"• Resolution: ✅ *Full Transport Charge Paid* (${existing.amount_charged_to_customer:,.2f})"
        elif existing.dispatch_option == "PARTIAL_CHARGE" or existing.status == "DISPATCHED_PARTIAL_CHARGE":
            res_summary = (
                f"• Resolution: ✅ *Partial Transport Charge*\n"
                f"• Customer Paid: ${existing.amount_charged_to_customer:,.2f}\n"
                f"• Pending Recorded: ${existing.pending_balance_recorded:,.2f}"
            )
        elif existing.dispatch_option == "FULL_TO_PENDING" or existing.status == "DISPATCHED_FULL_PENDING":
            res_summary = (
                f"• Resolution: ✅ *Full to Pending Balance*\n"
                f"• Pending Recorded: ${existing.pending_balance_recorded:,.2f}"
            )
        else:
            res_summary = f"• Resolution: ✅ *{existing.status}*"

        body = (
            f"🔒 *TRIP ALREADY APPROVED & DISPATCHED*\n"
            f"────────────────────\n"
            f"🚛 *Trip ID:* `{existing.trip_id}`\n"
            f"📍 *Destination:* {existing.destination_city}\n"
            f"💰 *Trip Sales Value:* ${existing.trip_sales_value:,.2f}\n"
            f"📅 *Processed:* {formatted_date}\n"
            f"👤 *Authorized By:* {sales_name} (`+{existing.salesperson_phone}`)\n"
            f"────────────────────\n"
            f"📊 *Current Status:* ✅ *ALREADY APPROVED*\n"
            f"{res_summary}\n\n"
            f"⚠️ *Notice:* Each Trip ID can only be entered once. This trip is already cleared for dispatch."
        )
        buttons = [
            {"id": "btn_domain_fleet", "title": "🚛 Verify Another"},
            {"id": "btn_sales_menu", "title": "↩️ Main Menu"}
        ]
        await meta_api.send_button_message(
            to_phone=phone,
            body_text=body,
            buttons=buttons,
            header_text="🔒 TRIP ALREADY PROCESSED"
        )
        return True

    # Not dispatched yet (either shortfall pending resolution, or threshold passed awaiting dispatch)
    clean_btn_id = re.sub(r"[^\w-]", "", existing.trip_id)[:40]
    if not existing.has_shortfall:
        # Trip passed threshold, awaiting user to click Dispatch or Add Transport
        cur_pending = await get_sales_rep_pending_balance(session, phone)
        pending_notice = ""
        if cur_pending > 0:
            pending_notice = (
                f"\n\n⚖️ *Your Pending Balance:* *${cur_pending:,.2f}*\n"
                f"💡 _Did customer pay transport? Tap *Add Transport* below to reduce your pending balance!_"
            )
        body = (
            f"✅ *FLEET TRIP APPROVED FOR DISPATCH*\n"
            f"────────────────────\n"
            f"🚛 *Trip:* `{existing.trip_id}`\n"
            f"📍 *Destination:* {existing.destination_city}\n"
            f"💰 *Trip Total Sales:* ${existing.trip_sales_value:,.2f}\n"
            f"🎯 *Required Minimum:* ${existing.required_minimum:,.2f}\n"
            f"📊 *Status:* ✅ *Passed Minimum Sales Threshold*\n"
            f"────────────────────\n"
            f"🎉 Trip meets all sales requirements! Cleared for driver dispatch and vehicle loading.{pending_notice}"
        )
        buttons = [
            {"id": f"btn_dispatch_{clean_btn_id}", "title": "🚛 Dispatch Trip"},
            {"id": f"btn_add_trans_{clean_btn_id}", "title": "💵 Add Transport"},
            {"id": "btn_sales_menu", "title": "↩️ Main Menu"}
        ]
        await set_user_state(
            session,
            phone,
            "awaiting_decision",
            {
                "trip_id": existing.trip_id,
                "clean_btn_id": clean_btn_id,
                "cur_pending": cur_pending,
                "dest": existing.destination_city,
                "sales_val": existing.trip_sales_value
            },
            flow_name="fleet_approval"
        )
        await meta_api.send_button_message(
            to_phone=phone,
            body_text=body,
            buttons=buttons,
            header_text="✅ TRIP APPROVED"
        )
        return True

    if is_same_user:
        body = (
            f"⚠️ *TRIP ALREADY ENTERED (NOT APPROVED YET)*\n"
            f"────────────────────\n"
            f"🚛 *Trip:* `{existing.trip_id}`\n"
            f"📍 *Destination:* {existing.destination_city}\n"
            f"💰 *Sales Total:* ${existing.trip_sales_value:,.2f}\n"
            f"💸 *Transport Fee to Take:* *${existing.transport_charge:,.2f}*\n"
            f"📅 *Submitted:* {formatted_date}\n"
            f"👤 *Submitted By:* You (`+{existing.salesperson_phone}`)\n"
            f"────────────────────\n"
            f"📊 *Current Status:* ❌ *NOT APPROVED (Pending Resolution)*\n\n"
            f"⚠️ *Action Required:* You previously submitted this trip. Each trip can only be entered once.\n"
            f"Please select how transport fee will be handled:\n\n"
            f"• *Full Charge:* Customer paid in full.\n"
            f"• *Partial Charge:* Customer paid part; remainder recorded to your pending balance.\n"
            f"• *Add to Pending:* Full ${existing.transport_charge:,.2f} recorded to your pending balance."
        )
        buttons = [
            {"id": f"flt_sf_full_{clean_btn_id}", "title": "Full Charge"},
            {"id": f"flt_sf_part_{clean_btn_id}", "title": "Partial Charge"},
            {"id": f"flt_sf_pend_{clean_btn_id}", "title": "Add to Pending"}
        ]
        await set_user_state(
            session,
            phone,
            "awaiting_shortfall_decision",
            {"trip_id": existing.trip_id, "required_charge": existing.transport_charge, "clean_btn_id": clean_btn_id},
            flow_name="fleet_approval"
        )
        await meta_api.send_button_message(
            to_phone=phone,
            body_text=body,
            buttons=buttons,
            header_text="⚠️ TRIP NOT APPROVED"
        )
        return True
    else:
        await clear_user_state(session, phone)
        body = (
            f"🔒 *TRIP ALREADY ENTERED BY ANOTHER REP*\n"
            f"────────────────────\n"
            f"🚛 *Trip ID:* `{existing.trip_id}`\n"
            f"📍 *Destination:* {existing.destination_city}\n"
            f"💰 *Trip Total Sales:* ${existing.trip_sales_value:,.2f}\n"
            f"📅 *Submitted:* {formatted_date}\n"
            f"👤 *Submitted By:* {sales_name} (`+{existing.salesperson_phone}`)\n"
            f"────────────────────\n"
            f"📊 *Current Status:* ❌ *NOT APPROVED (Pending Resolution)*\n\n"
            f"⚠️ *Notice:* This trip was already entered by {sales_name} and is currently awaiting their resolution.\n"
            f"To prevent duplicate records, each trip can only be processed once."
        )
        buttons = [
            {"id": "btn_domain_fleet", "title": "🚛 Verify Another"},
            {"id": "btn_sales_menu", "title": "↩️ Main Menu"}
        ]
        await meta_api.send_button_message(
            to_phone=phone,
            body_text=body,
            buttons=buttons,
            header_text="🔒 TRIP ALREADY ENTERED"
        )
        return True


async def handle_fleet_approval_flow(
    session: AsyncSession,
    phone: str,
    employee: Optional[Employee],
    message_text: str,
    state: Optional[ConversationState]
) -> bool:
    """
    Handles WhatsApp message flow for Fleet Approval (Trip verification, shortfall 3 options, pending ledger & recovery).
    Returns True if handled, False otherwise.
    """
    text_strip = message_text.strip()
    text_lower = text_strip.lower()
    clean_kw = re.sub(r"[^\w\s]", "", text_lower).strip()

    # Global Return to Sales Menu / Greetings / Resets
    if (
        clean_kw in GLOBAL_RESET_KEYWORDS
        or text_lower in GLOBAL_RESET_KEYWORDS
        or any(clean_kw.startswith(g + " ") for g in ["hi", "hello", "hey"])
        or text_lower in {"btn_sales_menu", "sales menu", "/menu", "/start", "main menu"}
    ):
        await clear_user_state(session, phone)
        await send_sales_portal_menu(session, phone, employee)
        return True

    # 1. User taps [ 🚛 Fleet Approval ] button or types 1
    if text_lower in {"btn_domain_fleet", "fleet approval", "🚛 fleet approval", "fleet", "trip approval", "1", "1️⃣", "1️⃣ fleet trip approval"}:
        await set_user_state(session, phone, "awaiting_company_selection", {}, flow_name="fleet_approval")
        header = "SELECT COMPANY"
        body = (
            "🏢 *SELECT COMPANY*\n"
            "────────────────────\n"
            "Please select the company for this fleet trip:"
        )
        buttons = [
            {"id": "flt_co_tg", "title": "A. TG Hardware"},
            {"id": "flt_co_lg", "title": "B. LG Plast"},
            {"id": "flt_co_kr", "title": "C. Kreckle"}
        ]
        await meta_api.send_button_message(
            to_phone=phone,
            body_text=body,
            buttons=buttons,
            header_text=header
        )
        return True

    # 1.1 Company Selection button or reply
    if text_lower in {"flt_co_tg", "flt_co_lg", "flt_co_kr"} or (
        state and state.flow_name == "fleet_approval" and state.current_step == "awaiting_company_selection"
    ):
        co_map = {
            "flt_co_tg": "A. TG Hardware",
            "flt_co_lg": "B. LG Plast",
            "flt_co_kr": "C. Kreckle"
        }
        company_name = co_map.get(text_lower)
        if not company_name:
            if "tg" in text_lower or "hardware" in text_lower or text_lower == "a":
                company_name = "A. TG Hardware"
            elif "lg" in text_lower or "plast" in text_lower or text_lower == "b":
                company_name = "B. LG Plast"
            elif "kreckle" in text_lower or text_lower == "c":
                company_name = "C. Kreckle"
            else:
                company_name = "A. TG Hardware"

        await set_user_state(
            session,
            phone,
            "awaiting_trip_id",
            {"company_name": company_name},
            flow_name="fleet_approval"
        )
        prompt = (
            f"🚛 *FLEET TRIP APPROVAL: {company_name}*\n"
            "────────────────────\n"
            "Please enter the *Trip ID* from Favlogix:\n\n"
            "_(e.g. `20042026-BINDURA` or `TRIP-2026-00456`)_\n\n"
            "💡 _Reply 'cancel' to return to the main menu._"
        )
        await meta_api.send_text_message(phone, prompt)
        return True

    # 2. User taps [ ⚖️ Pending Balance ] or types 2
    if text_lower in {"btn_sales_pending_menu", "pending balance", "pending", "balance", "ledger", "⚖️ pending balance", "2", "2️⃣", "2️⃣ pending balance", "4"}:
        await send_pending_balance_menu(session, phone, employee)
        return True

    # 3. User taps [ 💻 IT Support ] button or types 3
    if text_lower in {"btn_domain_it", "it support", "it", "💻 it support", "3", "3️⃣", "3️⃣ it support ticket"}:
        from app.handlers.flow_handler import send_categories_menu
        await clear_user_state(session, phone)
        await send_categories_menu(session, phone, domain="IT", data={"domain": "IT"})
        return True

    # 4. Check Pending Balance Details
    if text_lower in {"btn_pending_check_balance", "my pending total", "check pending", "pending total", "my pending", "📊 my pending total"}:
        await handle_check_pending_balance(session, phone, employee)
        return True

    # 3. Record Recovery Initiation
    if text_lower in {"btn_pending_record_recovery", "record recovery", "amount recovered", "recovery", "💵 record recovery"}:
        await set_user_state(session, phone, "awaiting_recovery_trip_id", {}, flow_name="fleet_pending")
        prompt = (
            "💵 *RECORD TRIP RECOVERY*\n"
            "────────────────────\n"
            "Please enter the *Trip ID* from which surplus recovery was made:\n\n"
            "_(e.g., `08042026-BYO` or `20042026-BINDURA`)_\n\n"
            "💡 _Reply 'cancel' to return to the main menu._"
        )
        await meta_api.send_text_message(phone, prompt)
        return True

    # 4. Handle Pending Recovery Active States
    if state and state.flow_name == "fleet_pending":
        if (
            clean_kw in GLOBAL_RESET_KEYWORDS
            or text_lower in GLOBAL_RESET_KEYWORDS
            or text_lower in {"cancel", "reset", "menu", "back", "exit"}
        ):
            await clear_user_state(session, phone)
            await send_sales_portal_menu(session, phone, employee)
            return True

        if state.current_step == "awaiting_recovery_trip_id":
            trip_id = text_strip.upper().replace("TRIP-", "").strip()
            # Guard against greetings, non-trip words, or short text
            if (
                len(trip_id) < 3
                or text_lower in GLOBAL_RESET_KEYWORDS
                or text_lower in {"ok", "okay", "yes", "no", "thanks", "thank you", "sure"}
            ):
                await meta_api.send_text_message(
                    phone,
                    "⚠️ Please enter a valid Trip ID (e.g. *08042026-BYO* or *20042026-BINDURA*), or reply *cancel* to return to the main menu."
                )
                return True

            cur_bal = await get_sales_rep_pending_balance(session, phone)
            await set_user_state(
                session,
                phone,
                "awaiting_recovery_amount",
                {"recovery_trip_id": trip_id, "cur_bal": cur_bal},
                flow_name="fleet_pending"
            )
            prompt = (
                f"💵 *RECORD TRIP RECOVERY*\n"
                f"────────────────────\n"
                f"🚛 *Trip:* `{trip_id}`\n"
                f"⚖️ *Current Pending Balance:* ${cur_bal:,.2f}\n\n"
                f"Please enter the *amount recovered* from this trip to deduct from your pending balance:\n\n"
                f"_(e.g. `50` or `125.50`)_\n\n"
                f"💡 _Reply 'cancel' to exit._"
            )
            await meta_api.send_text_message(phone, prompt)
            return True

        if state.current_step == "awaiting_recovery_amount":
            clean_val = re.sub(r"[^\d.]", "", text_strip)
            try:
                recovered_amt = float(clean_val)
                if recovered_amt <= 0:
                    raise ValueError()
            except ValueError:
                await meta_api.send_text_message(
                    phone,
                    "⚠️ Please enter a valid positive number for the amount recovered (e.g. `50` or `125.50`):"
                )
                return True

            data = state.current_data or {}
            trip_id = data.get("recovery_trip_id", "TRIP")
            cur_bal = data.get("cur_bal", await get_sales_rep_pending_balance(session, phone))
            recovered_amt = round(recovered_amt, 2)

            await record_pending_ledger_entry(
                session=session,
                phone=phone,
                name=employee.full_name if employee else "Sales Colleague",
                trip_id=trip_id,
                entry_type="RECOVERY_SURPLUS",
                amount=-recovered_amt,
                notes=f"Surplus recovered from trip {trip_id}"
            )
            new_bal = await get_sales_rep_pending_balance(session, phone)
            await clear_user_state(session, phone)

            receipt = (
                f"✅ *RECOVERY RECORDED SUCCESSFULLY*\n"
                f"────────────────────\n"
                f"👤 *Sales Rep:* {employee.full_name if employee else 'Sales Colleague'}\n"
                f"🚛 *Trip:* `{trip_id}`\n"
                f"💵 *Amount Recovered:* ${recovered_amt:,.2f}\n"
                f"⚖️ *Previous Pending:* ${cur_bal:,.2f}\n"
                f"🎯 *Updated Net Pending Balance:* *${new_bal:,.2f}*\n"
                f"────────────────────\n"
                f"Ledger updated! Surplus has been deducted from your pending recovery balance."
            )
            buttons = [
                {"id": "btn_pending_check_balance", "title": "📊 My Pending Total"},
                {"id": "btn_sales_menu", "title": "↩️ Main Menu"}
            ]
            await meta_api.send_button_message(
                to_phone=phone,
                body_text=receipt,
                buttons=buttons,
                header_text="💵 RECOVERY RECEIPT"
            )

            # Notify Sujit
            admin_msg = (
                f"📢 *FLEET: PENDING BALANCE RECOVERY*\n"
                f"────────────────────\n"
                f"🚛 *Trip:* `{trip_id}`\n"
                f"👤 *Sales Rep:* {employee.full_name if employee else 'Sales Colleague'} (`+{phone}`)\n"
                f"💵 *Surplus Recovered:* ${recovered_amt:,.2f}\n"
                f"⚖️ *Previous Pending:* ${cur_bal:,.2f}\n"
                f"🎯 *Updated Net Pending Balance:* ${new_bal:,.2f}\n"
                f"────────────────────\n"
                f"Deducted from sales rep pending ledger."
            )
            await notify_fleet_admin(admin_msg)
            return True

    # 5. User taps [ 🚛 Fleet Approval ] button or types command
    if text_lower in {"btn_domain_fleet", "fleet approval", "🚛 fleet approval", "fleet", "trip approval"}:
        await set_user_state(session, phone, "awaiting_trip_id", {}, flow_name="fleet_approval")
        prompt = (
            "🚛 *FLEET TRIP APPROVAL REQUEST*\n"
            "────────────────────\n"
            "Please enter the *Trip ID* or *Trip Name* from Favlogix:\n\n"
            "_(e.g., `20042026-BINDURA` or `TRIP-20042026-BINDURA`)_\n\n"
            "💡 _Reply 'cancel' or 'menu' to return to the main menu._"
        )
        await meta_api.send_text_message(phone, prompt)
        return True

    # 6. Standard Dispatch Button (For trips passing minimum sales threshold)
    if text_lower.startswith(("flt_disp_ok_", "btn_accept_fleet_", "btn_dispatch_")):
        trip_id = text_strip.replace("flt_disp_ok_", "").replace("btn_accept_fleet_", "").replace("btn_dispatch_", "").strip()
        data = (state.current_data or {}) if state else {}
        if not data.get("trip_id"):
            data["trip_id"] = trip_id
        clean_btn_id = data.get("clean_btn_id", trip_id)

        data["charged_amount"] = 0.0
        data["pending_amount"] = 0.0
        data["transport_charge"] = 0.0

        await set_user_state(session, phone, "awaiting_favlogix_charged", data, flow_name="fleet_approval")
        prompt = (
            f"✅ *TRIP VERIFICATION PASSED: {trip_id}*\n"
            "────────────────────\n"
            "Please charge all customers in Favlogix and select YES when done:"
        )
        buttons = [
            {"id": f"flt_chg_yes_{clean_btn_id}", "title": "YES"},
            {"id": f"flt_chg_no_{clean_btn_id}", "title": "NO"}
        ]
        await meta_api.send_button_message(to_phone=phone, body_text=prompt, buttons=buttons, header_text="FAVLOGIX CHARGES")
        return True

    # 6.5. Add Transport Charge Button (When shortfall is not there, sales can add transport charge to reduce pending balance)
    if text_lower.startswith("btn_add_trans_") or (
        state and state.flow_name == "fleet_approval" and state.current_step == "awaiting_decision" and text_lower in {"add transport", "transport charge", "reduce pending", "add charge", "2", "2️⃣"}
    ):
        trip_id = ""
        clean_btn_id = ""
        dest = ""
        sales_val = 0.0
        cur_pending = 0.0

        if state and state.current_data:
            trip_id = state.current_data.get("trip_id", "")
            clean_btn_id = state.current_data.get("clean_btn_id", "")
            dest = state.current_data.get("dest", "")
            sales_val = float(state.current_data.get("sales_val", 0.0))
            cur_pending = float(state.current_data.get("cur_pending", 0.0))

        if not trip_id and text_lower.startswith("btn_add_trans_"):
            clean_id = text_strip.replace("btn_add_trans_", "").strip()
            rec_chk = (await session.execute(
                select(FleetTripApproval).where(FleetTripApproval.trip_id.ilike(f"%{clean_id}%")).order_by(FleetTripApproval.id.desc())
            )).scalars().first()
            if rec_chk:
                trip_id = rec_chk.trip_id
                clean_btn_id = clean_id
                dest = rec_chk.destination_city
                sales_val = rec_chk.trip_sales_value

        if cur_pending <= 0.0:
            cur_pending = await get_sales_rep_pending_balance(session, phone)

        await set_user_state(
            session,
            phone,
            "awaiting_surplus_transport_charge",
            {
                "trip_id": trip_id,
                "clean_btn_id": clean_btn_id,
                "cur_pending": cur_pending,
                "dest": dest,
                "sales_val": sales_val
            },
            flow_name="fleet_approval"
        )
        prompt = (
            f"💵 *ADD TRANSPORT CHARGE / REDUCE PENDING*\n"
            f"────────────────────\n"
            f"🚛 *Trip:* `{trip_id}`\n"
            f"📍 *Destination:* {dest}\n"
            f"💰 *Trip Sales Value:* ${sales_val:,.2f}\n"
            f"⚖️ *Your Current Pending Balance:* *${cur_pending:,.2f}*\n"
            f"────────────────────\n"
            f"Please enter the *transport charge amount* collected to apply against your pending balance:\n"
            f"_(e.g. `50` or `125.00`)_\n\n"
            f"💡 _This amount will reduce your pending balance and record surplus recovery on trip `{trip_id}`._\n"
            f"💡 _Reply 'cancel' to return to the main menu._"
        )
        await meta_api.send_text_message(phone, prompt)
        return True

    # 6.6. Handle received transport charge amount
    if state and state.flow_name == "fleet_approval" and state.current_step == "awaiting_surplus_transport_charge":
        if text_lower in {"cancel", "reset", "menu", "back", "exit"}:
            await clear_user_state(session, phone)
            await send_sales_portal_menu(session, phone, employee)
            return True

        clean_val = re.sub(r"[^\d.]", "", text_strip)
        try:
            trans_amt = float(clean_val)
            if trans_amt <= 0:
                raise ValueError()
        except ValueError:
            await meta_api.send_text_message(
                phone,
                "⚠️ Please enter a valid positive number for the transport charge amount (e.g. `50` or `125.00`):"
            )
            return True

        data = state.current_data or {}
        trip_id = data.get("trip_id", "")
        dest = data.get("dest", "")
        sales_val = float(data.get("sales_val", 0.0))
        cur_pending = float(data.get("cur_pending", 0.0))
        trans_amt = round(trans_amt, 2)

        # Check if already dispatched
        rec = None
        if trip_id:
            rec_stmt = select(FleetTripApproval).where(FleetTripApproval.trip_id == trip_id).order_by(FleetTripApproval.id.desc())
            rec = (await session.execute(rec_stmt)).scalars().first()
            if rec and (rec.status in {"DISPATCHED", "DISPATCHED_WITH_TRANSPORT_CHARGE"} or rec.dispatch_option is not None):
                await handle_existing_trip_response(session, phone, employee, rec)
                return True

        # Record surplus recovery in pending ledger (reduces balance)
        await record_pending_ledger_entry(
            session=session,
            phone=phone,
            name=employee.full_name if employee else "Sales Colleague",
            trip_id=trip_id,
            entry_type="RECOVERY_SURPLUS",
            amount=-trans_amt,
            notes=f"Transport charge added on trip {trip_id} to reduce pending"
        )

        # Update FleetTripApproval
        if rec:
            rec.status = "DISPATCHED_WITH_TRANSPORT_CHARGE"
            rec.amount_charged_to_customer = trans_amt
            rec.pending_balance_recorded = -trans_amt
            rec.dispatch_option = "APPROVED_WITH_TRANSPORT_RECOVERY"
            await session.commit()

        new_pending = await get_sales_rep_pending_balance(session, phone)
        await clear_user_state(session, phone)

        ack = (
            f"✅ *TRIP DISPATCH AUTHORIZED (TRANSPORT CHARGE ADDED)*\n"
            f"────────────────────\n"
            f"🚛 *Trip:* `{trip_id}`\n"
            f"💸 *Transport Charge Added:* ${trans_amt:,.2f}\n"
            f"⚖️ *Previous Pending Balance:* ${cur_pending:,.2f}\n"
            f"🎯 *Updated Net Pending Balance:* *${new_pending:,.2f}*\n"
            f"👤 *Authorized By:* {employee.full_name if employee else 'Sales Agent'} (`+{phone}`)\n"
            f"📊 *Status:* Cleared for Vehicle Loading & Dispatch 🚛💨\n\n"
            f"Order is clear to go! ${trans_amt:,.2f} has been deducted from your pending recovery balance."
        )
        buttons = [
            {"id": "btn_pending_check_balance", "title": "📊 My Pending Total"},
            {"id": "btn_sales_menu", "title": "↩️ Main Menu"}
        ]
        await meta_api.send_button_message(
            to_phone=phone,
            body_text=ack,
            buttons=buttons,
            header_text="✅ TRIP DISPATCH AUTHORIZED"
        )

        # Notify Sujit
        admin_alert = (
            f"📢 *FLEET DISPATCH: TRANSPORT CHARGE ADDED*\n"
            f"────────────────────\n"
            f"🚛 *Trip:* `{trip_id}`\n"
            f"📍 *Destination:* {dest}\n"
            f"👤 *Sales Rep:* {employee.full_name if employee else 'Sales'} (`+{phone}`)\n"
            f"💰 *Trip Total Sales:* ${sales_val:,.2f}\n"
            f"💸 *Transport Charge Added:* ${trans_amt:,.2f}\n"
            f"🎯 *Rep Remaining Pending Balance:* ${new_pending:,.2f}\n"
            f"📊 *Status:* Cleared for Loading & Dispatch 🚛💨"
        )
        await notify_fleet_admin(admin_alert)
        return True

    # 7. Shortfall Option 1: Full Charge Paid
    if text_lower.startswith(("flt_sf_full_", "btn_short_full_")) or (
        state and state.flow_name == "fleet_approval" and state.current_step == "awaiting_shortfall_decision" and text_lower in {"1", "1️⃣", "full", "full charge", "full charge paid"}
    ):
        data = state.current_data or {}
        trip_id = data.get("trip_id", "")
        req_charge = float(data.get("required_charge", 0.0))
        clean_btn_id = data.get("clean_btn_id", trip_id)

        if not trip_id and text_lower.startswith(("flt_sf_full_", "btn_short_full_")):
            clean_id = text_strip.replace("flt_sf_full_", "").replace("btn_short_full_", "").strip()
            rec_chk = (await session.execute(
                select(FleetTripApproval).where(FleetTripApproval.trip_id.ilike(f"%{clean_id}%")).order_by(FleetTripApproval.id.desc())
            )).scalars().first()
            if rec_chk:
                trip_id = rec_chk.trip_id
                req_charge = rec_chk.transport_charge
                clean_btn_id = clean_id
                data.update({
                    "trip_id": trip_id,
                    "clean_btn_id": clean_id,
                    "required_charge": req_charge,
                    "dest": rec_chk.destination_city,
                    "route": rec_chk.route or rec_chk.destination_city,
                    "sales_val": rec_chk.trip_sales_value,
                    "transport_charge": req_charge
                })

        # No need to ask amount because we know full charge is paid!
        data["charged_amount"] = req_charge
        data["pending_amount"] = 0.0

        await set_user_state(session, phone, "awaiting_favlogix_charged", data, flow_name="fleet_approval")
        prompt = (
            f"💵 *FULL TRANSPORT CHARGE SELECTED*\n"
            f"Trip: `{trip_id}` | Transport Fee: ${req_charge:,.2f}\n"
            "────────────────────\n"
            "Please charge all customers in Favlogix and select YES when done:"
        )
        buttons = [
            {"id": f"flt_chg_yes_{clean_btn_id}", "title": "YES"},
            {"id": f"flt_chg_no_{clean_btn_id}", "title": "NO"}
        ]
        await meta_api.send_button_message(to_phone=phone, body_text=prompt, buttons=buttons, header_text="FAVLOGIX CHARGES")
        return True

    # 8. Shortfall Option 2: Partial Charge Initiated
    if text_lower.startswith(("flt_sf_part_", "btn_short_part_")) or (
        state and state.flow_name == "fleet_approval" and state.current_step == "awaiting_shortfall_decision" and text_lower in {"2", "2️⃣", "partial", "partial charge"}
    ):
        data = state.current_data or {}
        trip_id = data.get("trip_id", "")
        req_charge = float(data.get("required_charge", 0.0))
        clean_btn_id = data.get("clean_btn_id", trip_id)

        if not trip_id and text_lower.startswith(("flt_sf_part_", "btn_short_part_")):
            clean_id = text_strip.replace("flt_sf_part_", "").replace("btn_short_part_", "").strip()
            rec_chk = (await session.execute(
                select(FleetTripApproval).where(FleetTripApproval.trip_id.ilike(f"%{clean_id}%")).order_by(FleetTripApproval.id.desc())
            )).scalars().first()
            if rec_chk:
                trip_id = rec_chk.trip_id
                req_charge = rec_chk.transport_charge
                clean_btn_id = clean_id
                data.update({
                    "trip_id": trip_id,
                    "clean_btn_id": clean_id,
                    "required_charge": req_charge,
                    "dest": rec_chk.destination_city,
                    "route": rec_chk.route or rec_chk.destination_city,
                    "sales_val": rec_chk.trip_sales_value,
                    "transport_charge": req_charge
                })

        await set_user_state(
            session,
            phone,
            "awaiting_partial_charge",
            data,
            flow_name="fleet_approval"
        )
        prompt = (
            f"💵 *PARTIAL TRANSPORT CHARGE: {trip_id}*\n"
            f"Transport Fee: ${req_charge:,.2f}\n"
            "────────────────────\n"
            "Please enter the amount charged to customer in USD:\n"
            "_(e.g. 50.00)_"
        )
        await meta_api.send_text_message(phone, prompt)
        return True

    # 9. Shortfall Option 2: Partial Charge Amount Received
    if state and state.flow_name == "fleet_approval" and state.current_step == "awaiting_partial_charge":
        if text_lower in {"cancel", "reset", "menu", "back", "exit"}:
            await clear_user_state(session, phone)
            await send_sales_portal_menu(session, phone, employee)
            return True

        clean_val = re.sub(r"[^\d.]", "", text_strip)
        try:
            charged_amt = float(clean_val)
            if charged_amt < 0:
                raise ValueError()
        except ValueError:
            await meta_api.send_text_message(
                phone,
                "⚠️ Please enter a valid number for the amount charged (e.g. 50.00):"
            )
            return True

        data = state.current_data or {}
        trip_id = data.get("trip_id", "")
        clean_btn_id = data.get("clean_btn_id", trip_id)
        required_charge = float(data.get("required_charge", 0.0))
        charged_amt = round(charged_amt, 2)

        remaining_pending = max(0.0, round(required_charge - charged_amt, 2))
        if remaining_pending > 0:
            await record_pending_ledger_entry(
                session=session,
                phone=phone,
                name=employee.full_name if employee else "Sales Colleague",
                trip_id=trip_id,
                entry_type="SHORTFALL_PARTIAL_BALANCE",
                amount=remaining_pending,
                notes=f"Partial charge deficit on trip {trip_id}"
            )

        data["charged_amount"] = charged_amt
        data["pending_amount"] = remaining_pending

        await set_user_state(session, phone, "awaiting_favlogix_charged", data, flow_name="fleet_approval")
        prompt = (
            f"💵 Charged: ${charged_amt:,.2f} | Remaining ${remaining_pending:,.2f} added to pending balance.\n"
            "────────────────────\n"
            "Please charge all customers in Favlogix and select YES when done:"
        )
        buttons = [
            {"id": f"flt_chg_yes_{clean_btn_id}", "title": "YES"},
            {"id": f"flt_chg_no_{clean_btn_id}", "title": "NO"}
        ]
        await meta_api.send_button_message(to_phone=phone, body_text=prompt, buttons=buttons, header_text="FAVLOGIX CHARGES")
        return True

    # 10. Shortfall Option 3: Full to Pending
    if text_lower.startswith(("flt_sf_pend_", "btn_short_none_")) or (
        state and state.flow_name == "fleet_approval" and state.current_step == "awaiting_shortfall_decision" and text_lower in {"3", "3️⃣", "pending", "add to pending", "full to pending", "none"}
    ):
        data = state.current_data or {}
        trip_id = data.get("trip_id", "")
        clean_btn_id = data.get("clean_btn_id", trip_id)
        req_charge = float(data.get("required_charge", 0.0))

        if not trip_id and text_lower.startswith(("flt_sf_pend_", "btn_short_none_")):
            clean_id = text_strip.replace("flt_sf_pend_", "").replace("btn_short_none_", "").strip()
            rec_chk = (await session.execute(
                select(FleetTripApproval).where(FleetTripApproval.trip_id.ilike(f"%{clean_id}%")).order_by(FleetTripApproval.id.desc())
            )).scalars().first()
            if rec_chk:
                trip_id = rec_chk.trip_id
                req_charge = rec_chk.transport_charge
                clean_btn_id = clean_id
                data.update({
                    "trip_id": trip_id,
                    "clean_btn_id": clean_id,
                    "required_charge": req_charge,
                    "dest": rec_chk.destination_city,
                    "route": rec_chk.route or rec_chk.destination_city,
                    "sales_val": rec_chk.trip_sales_value,
                    "transport_charge": req_charge
                })

        # No need to ask amount; full transport charge added to pending ledger
        await record_pending_ledger_entry(
            session=session,
            phone=phone,
            name=employee.full_name if employee else "Sales Colleague",
            trip_id=trip_id,
            entry_type="SHORTFALL_FULL_UNCHARGED",
            amount=req_charge,
            notes=f"Uncharged transport charge on trip {trip_id}"
        )

        data["charged_amount"] = 0.0
        data["pending_amount"] = req_charge

        await set_user_state(session, phone, "awaiting_favlogix_charged", data, flow_name="fleet_approval")
        prompt = (
            f"⚖️ Full transport fee of ${req_charge:,.2f} added to your pending recovery balance.\n"
            "────────────────────\n"
            "Please charge all customers in Favlogix and select YES when done:"
        )
        buttons = [
            {"id": f"flt_chg_yes_{clean_btn_id}", "title": "YES"},
            {"id": f"flt_chg_no_{clean_btn_id}", "title": "NO"}
        ]
        await meta_api.send_button_message(to_phone=phone, body_text=prompt, buttons=buttons, header_text="FAVLOGIX CHARGES")
        return True

    # 10.5 Stage 2: Favlogix Charged Confirmation [YES] / [NO]
    if text_lower.startswith("flt_chg_yes_") or (
        state and state.flow_name == "fleet_approval" and state.current_step == "awaiting_favlogix_charged" and text_lower in {"yes", "y", "done"}
    ):
        data = state.current_data or {}
        trip_id = data.get("trip_id", "")
        if not trip_id and text_lower.startswith("flt_chg_yes_"):
            trip_id = text_strip.replace("flt_chg_yes_", "").strip()
            data["trip_id"] = trip_id

        await set_user_state(session, phone, "awaiting_customer_manifest", data, flow_name="fleet_approval")
        prompt = (
            f"📋 *CUSTOMER CHARGES MANIFEST: {trip_id}*\n"
            "────────────────────\n"
            "To verify customer charges autonomously during driver transit, please enter customer charges in this format:\n\n"
            "👉 `CUST-101: 45, CUST-102: 60`\n\n"
            "_(or type *SKIP* if charging a single general customer)_"
        )
        await meta_api.send_text_message(phone, prompt)
        return True

    if text_lower.startswith("flt_chg_no_") or (
        state and state.flow_name == "fleet_approval" and state.current_step == "awaiting_favlogix_charged" and text_lower in {"no", "n"}
    ):
        data = state.current_data or {}
        trip_id = data.get("trip_id", "")
        clean_btn_id = data.get("clean_btn_id", trip_id)
        prompt = (
            "⚠️ Please charge all customers in Favlogix first.\n\n"
            "Select *YES* below once all charges have been entered in Favlogix:"
        )
        buttons = [
            {"id": f"flt_chg_yes_{clean_btn_id}", "title": "YES"}
        ]
        await meta_api.send_button_message(to_phone=phone, body_text=prompt, buttons=buttons, header_text="FAVLOGIX CHARGES")
        return True

    # 10.6 Stage 2 Manifest Submission -> Save Schedules & Notify Edward
    if state and state.flow_name == "fleet_approval" and state.current_step == "awaiting_customer_manifest":
        data = state.current_data or {}
        trip_id = data.get("trip_id", "")
        company_name = data.get("company_name", "A. TG Hardware")
        dest = data.get("dest", "")
        route = data.get("route", dest)
        sales_val = float(data.get("sales_val", 0.0))
        transport_charge = float(data.get("transport_charge", 0.0))

        schedules = []
        raw_manifest = text_strip
        if raw_manifest.upper() == "SKIP" or ":" not in raw_manifest:
            schedules.append({
                "customer_id": "GENERAL",
                "expected_charge": transport_charge
            })
        else:
            items = re.split(r"[,;\n]+", raw_manifest)
            for item in items:
                if ":" in item:
                    c_id, amt_str = item.split(":", 1)
                    clean_c = c_id.strip().upper()
                    clean_amt = re.sub(r"[^\d.]", "", amt_str.strip())
                    try:
                        exp_amt = float(clean_amt)
                    except ValueError:
                        exp_amt = 0.0
                    if clean_c:
                        schedules.append({
                            "customer_id": clean_c,
                            "expected_charge": exp_amt
                        })

        if not schedules:
            schedules.append({
                "customer_id": "GENERAL",
                "expected_charge": transport_charge
            })

        # Save customer schedules batch
        await save_customer_schedules_batch(session, trip_id, schedules)

        # Create or update FleetTripRequest
        await create_or_update_fleet_trip_request(
            session=session,
            trip_id=trip_id,
            company_name=company_name,
            salesperson_phone=phone,
            destination_city=dest,
            salesperson_name=employee.full_name if employee else "Sales Colleague",
            route=route,
            trip_sales_value=sales_val,
            transport_charge=transport_charge
        )

        await clear_user_state(session, phone)

        ack = (
            f"✅ *TRIP DISPATCH CLEARED: {trip_id}*\n"
            "────────────────────\n"
            f"Company: {company_name}\n"
            f"Route: {route or dest}\n"
            f"Registered Customers: {len(schedules)}\n"
            "────────────────────\n"
            "Order is cleared! Notification forwarded to Edward for truck and driver allocation. 🚛💨"
        )
        buttons = [
            {"id": "btn_sales_menu", "title": "Main Menu"}
        ]
        await meta_api.send_button_message(to_phone=phone, body_text=ack, buttons=buttons, header_text="DISPATCH CLEARED")

        # Forward immediately to Edward for Stage 3!
        from app.handlers.logistics_handler import notify_edward_new_trip
        await notify_edward_new_trip(session, trip_id)
        return True

    # 11. Cancel button
    if text_lower.startswith("btn_cancel_fleet_"):
        await clear_user_state(session, phone)
        await meta_api.send_text_message(phone, "❌ *Trip request cancelled.* Returning to main menu.")
        await send_sales_portal_menu(session, phone, employee)
        return True

    # 12. Handle active state 'awaiting_trip_id'
    if state and state.flow_name == "fleet_approval" and state.current_step == "awaiting_trip_id":
        if (
            clean_kw in GLOBAL_RESET_KEYWORDS
            or text_lower in GLOBAL_RESET_KEYWORDS
            or any(clean_kw.startswith(g + " ") for g in ["hi", "hello", "hey"])
            or text_lower in {"cancel", "reset", "menu", "back", "exit"}
        ):
            await clear_user_state(session, phone)
            await send_sales_portal_menu(session, phone, employee)
            return True

        trip_query = text_strip.upper().replace("TRIP-", "").strip()
        if (
            len(trip_query) < 3
            or text_lower in GLOBAL_RESET_KEYWORDS
            or text_lower in {"ok", "okay", "yes", "no", "thanks", "thank you", "sure"}
        ):
            await meta_api.send_text_message(
                phone,
                "⚠️ Please enter a valid Trip ID (e.g. *20042026-BINDURA*), or reply *cancel* to return to the main menu."
            )
            return True

        # Check 1: Check if trip was already entered in database
        existing = await get_existing_trip_approval(session, trip_query)
        if existing:
            await handle_existing_trip_response(session, phone, employee, existing)
            return True

        # Send in-progress notification
        await meta_api.send_text_message(
            phone,
            f"⏳ *Verifying Trip `{trip_query}` with Favlogix ERP...*\n_Please wait while live order values and route thresholds are verified._"
        )

        # Call Trip Verification Service
        result = await trip_verification_service.verify_trip(trip_query)

        if not result.get("success"):
            err_msg = result.get("error", "Could not verify trip.")
            fail_card = (
                f"❌ *TRIP VERIFICATION ERROR*\n"
                f"────────────────────\n"
                f"⚠️ *Reason:* {err_msg}\n\n"
                f"Please check the Trip ID in Favlogix and try again, or reply *cancel* to return to the main menu."
            )
            await meta_api.send_text_message(phone, fail_card)
            return True

        # Successful verification -> Build Report Card & Persist in Database
        trip_id = result.get("trip_id", trip_query)

        # Check 2: Re-check if canonical trip ID resolved by Favlogix was already entered in database
        existing_canonical = await get_existing_trip_approval(session, trip_id)
        if existing_canonical:
            await handle_existing_trip_response(session, phone, employee, existing_canonical)
            return True

        company_name = (state.current_data or {}).get("company_name", "A. TG Hardware") if state else "A. TG Hardware"
        dest = result.get("destination_city", "Unknown")
        route = result.get("route", "")
        route_str = f" ({route})" if route else ""
        sales_val = result.get("total_amount", 0.0)
        req_min = result.get("required_minimum", 0.0)
        shortfall = result.get("shortfall", 0.0)
        transport_charge = result.get("transport_charge", 0.0)
        is_approved = result.get("approved", False)

        clean_btn_id = re.sub(r"[^\w-]", "", trip_id)[:40]

        if is_approved:
            approval_record = FleetTripApproval(
                trip_id=trip_id,
                salesperson_phone=phone,
                salesperson_name=employee.full_name if employee else "Sales Colleague",
                destination_city=dest,
                route=route,
                trip_sales_value=sales_val,
                required_minimum=req_min,
                shortfall=shortfall,
                transport_charge=transport_charge,
                amount_charged_to_customer=0.0,
                pending_balance_recorded=0.0,
                has_shortfall=False,
                dispatch_option=None,
                status="THRESHOLD_PASSED_AWAITING_DISPATCH",
                raw_data=result
            )
            session.add(approval_record)
            await session.commit()

            cur_pending = await get_sales_rep_pending_balance(session, phone)
            pending_notice = ""
            if cur_pending > 0:
                pending_notice = (
                    f"\n\n⚖️ *Your Pending Balance:* *${cur_pending:,.2f}*\n"
                    f"💡 _Did customer pay transport? Tap *Add Transport* below to reduce your pending balance!_"
                )

            card_body = (
                f"✅ *FLEET TRIP DETAILS*\n"
                f"────────────────────\n"
                f"🏢 *Company:* {company_name}\n"
                f"🚛 *Trip:* `{trip_id}`\n"
                f"📍 *Destination:* {dest}{route_str}\n"
                f"💰 *Sales Total:* ${sales_val:,.2f}\n"
                f"────────────────────\n"
                f"Trip meets route requirements! Cleared for dispatch.{pending_notice}"
            )
            buttons = [
                {"id": f"flt_disp_ok_{clean_btn_id}", "title": "Authorize Dispatch"},
                {"id": f"flt_add_trans_{clean_btn_id}", "title": "Add Transport"},
                {"id": "btn_sales_menu", "title": "Main Menu"}
            ]
            await set_user_state(
                session,
                phone,
                "awaiting_decision",
                {
                    "trip_id": trip_id,
                    "clean_btn_id": clean_btn_id,
                    "company_name": company_name,
                    "cur_pending": cur_pending,
                    "dest": dest,
                    "route": route,
                    "sales_val": sales_val,
                    "transport_charge": 0.0,
                    "required_charge": 0.0
                },
                flow_name="fleet_approval"
            )
            await meta_api.send_button_message(
                to_phone=phone,
                body_text=card_body,
                buttons=buttons,
                header_text="FLEET TRIP DETAILS"
            )
        else:
            # Shortfall detected -> Save record & Send 3 clean options
            # Hide route minimum, shortfall amount, and 4% formula as requested!
            approval_record = FleetTripApproval(
                trip_id=trip_id,
                salesperson_phone=phone,
                salesperson_name=employee.full_name if employee else "Sales Colleague",
                destination_city=dest,
                route=route,
                trip_sales_value=sales_val,
                required_minimum=req_min,
                shortfall=shortfall,
                transport_charge=transport_charge,
                amount_charged_to_customer=0.0,
                pending_balance_recorded=0.0,
                has_shortfall=True,
                status="SHORTFALL_PENDING_ACTION",
                raw_data=result
            )
            session.add(approval_record)
            await session.commit()

            card_body = (
                f"📋 *FLEET TRIP DETAILS*\n"
                f"────────────────────\n"
                f"🏢 *Company:* {company_name}\n"
                f"🚛 *Trip:* `{trip_id}`\n"
                f"📍 *Destination:* {dest}{route_str}\n"
                f"💰 *Sales Total:* ${sales_val:,.2f}\n"
                f"💸 *Transport Fee to Take:* *${transport_charge:,.2f}*\n"
                f"────────────────────\n"
                f"Please select an option below:"
            )
            buttons = [
                {"id": f"flt_sf_full_{clean_btn_id}", "title": "Full Charge"},
                {"id": f"flt_sf_part_{clean_btn_id}", "title": "Partial Charge"},
                {"id": f"flt_sf_pend_{clean_btn_id}", "title": "Add to Pending"}
            ]
            await set_user_state(
                session,
                phone,
                "awaiting_shortfall_decision",
                {
                    "trip_id": trip_id,
                    "clean_btn_id": clean_btn_id,
                    "company_name": company_name,
                    "dest": dest,
                    "route": route,
                    "sales_val": sales_val,
                    "transport_charge": transport_charge,
                    "required_charge": transport_charge
                },
                flow_name="fleet_approval"
            )
            await meta_api.send_button_message(
                to_phone=phone,
                body_text=card_body,
                buttons=buttons,
                header_text="FLEET TRIP DETAILS"
            )
        return True

    return False

