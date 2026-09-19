import logging
import re
from typing import Optional, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import (
    Employee, Department, ConversationState, FleetTripApproval,
    FleetPendingLedger, get_sales_rep_pending_balance,
    get_sales_rep_ledger_entries, record_pending_ledger_entry
)
from app.state_manager import set_user_state, clear_user_state, get_user_state
from app.meta_api import meta_api
from app.services.trip_verification_service import trip_verification_service

logger = logging.getLogger("fleet_approval_handler")

# In-memory role override cache for instant WhatsApp one-word role toggling
# Allows +919265368695 to switch live between "SALES" and "MASTER_ADMIN" via chat
SESSION_ROLE_OVERRIDES: Dict[str, str] = {}


def is_valid_phone(phone_str: Optional[str]) -> bool:
    """Returns True if phone_str contains a valid international E.164 phone format (digits only)."""
    if not phone_str:
        return False
    cleaned = phone_str.replace("+", "").strip()
    return bool(cleaned.isdigit() and 7 <= len(cleaned) <= 15)



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
    if cmd in {"role sales", "switch sales", "mode sales", "test sales"}:
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
    Presents the salesperson 3-button menu:
    1. [ 💻 IT Support ]
    2. [ 🚛 Fleet Approval ]
    3. [ ⚖️ Pending Balance ]
    """
    name = employee.full_name if employee else "Sales Colleague"
    header = "🏢 TAGONESWA SALES PORTAL"
    body = (
        f"👋 Hello *{name}*!\n\n"
        f"Welcome to the Tagoneswa Support Portal.\n\n"
        f"Please select the service you would like to access:"
    )
    footer = "Tap a button below to proceed"
    buttons = [
        {"id": "btn_domain_it", "title": "💻 IT Support"},
        {"id": "btn_domain_fleet", "title": "🚛 Fleet Approval"},
        {"id": "btn_sales_pending_menu", "title": "⚖️ Pending Balance"}
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

    # Global Return to Sales Menu
    if text_lower in {"btn_sales_menu", "sales menu"}:
        await clear_user_state(session, phone)
        await send_sales_portal_menu(session, phone, employee)
        return True

    # 1. User taps [ ⚖️ Pending Balance ] or types balance keywords
    if text_lower in {"btn_sales_pending_menu", "pending balance", "pending", "balance", "ledger", "⚖️ pending balance"}:
        await send_pending_balance_menu(session, phone, employee)
        return True

    # 2. Check Pending Balance
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
        if text_lower in {"cancel", "reset", "menu", "back", "exit"}:
            await clear_user_state(session, phone)
            await send_sales_portal_menu(session, phone, employee)
            return True

        if state.current_step == "awaiting_recovery_trip_id":
            trip_id = text_strip.upper().replace("TRIP-", "").strip()
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
    if text_lower.startswith(("btn_accept_fleet_", "btn_dispatch_")):
        trip_id = text_strip.replace("btn_accept_fleet_", "").replace("btn_dispatch_", "").strip()
        await clear_user_state(session, phone)

        rec_stmt = (
            select(FleetTripApproval)
            .where(FleetTripApproval.trip_id == trip_id)
            .order_by(FleetTripApproval.id.desc())
        )
        rec = (await session.execute(rec_stmt)).scalars().first()
        if rec:
            rec.status = "DISPATCHED"
            rec.dispatch_option = "APPROVED_THRESHOLD"
            await session.commit()

        ack = (
            f"✅ *TRIP DISPATCH AUTHORIZED*\n"
            f"────────────────────\n"
            f"🚛 *Trip:* `{trip_id}`\n"
            f"👤 *Authorized By:* {employee.full_name if employee else 'Sales Agent'} (`+{phone}`)\n"
            f"📊 *Status:* Cleared for Vehicle Loading & Dispatch\n\n"
            f"Notification has been logged for Logistics & Dispatch team! 🚛💨"
        )
        await meta_api.send_text_message(phone, ack)
        if is_valid_phone(settings.master_group_phone):
            try:
                group_alert = (
                    f"📢 *NEW FLEET DISPATCH APPROVED*\n"
                    f"• Trip: `{trip_id}`\n"
                    f"• Approver: {employee.full_name if employee else 'Sales'} (`+{phone}`)\n"
                    f"• Threshold: Passed Minimum Sales"
                )
                await meta_api.send_text_message(settings.master_group_phone, group_alert)
            except Exception as e:
                logger.warning(f"Could not alert master group of fleet approval: {e}")
        return True

    # 7. Shortfall Option 1: Full Charge Paid
    if text_lower.startswith("btn_short_full_") or (
        state and state.flow_name == "fleet_approval" and state.current_step == "awaiting_shortfall_decision" and text_lower in {"1", "1️⃣", "full", "full charge", "full charge paid"}
    ):
        trip_id = ""
        required_charge = 0.0
        if state and state.current_data:
            trip_id = state.current_data.get("trip_id", "")
            required_charge = float(state.current_data.get("required_charge", 0.0))

        if not trip_id and text_lower.startswith("btn_short_full_"):
            clean_id = text_strip.replace("btn_short_full_", "").strip()
            rec_chk = (await session.execute(
                select(FleetTripApproval).where(FleetTripApproval.trip_id.ilike(f"%{clean_id}%")).order_by(FleetTripApproval.id.desc())
            )).scalars().first()
            if rec_chk:
                trip_id = rec_chk.trip_id
                required_charge = rec_chk.transport_charge

        await clear_user_state(session, phone)

        if trip_id:
            rec_stmt = select(FleetTripApproval).where(FleetTripApproval.trip_id == trip_id).order_by(FleetTripApproval.id.desc())
            rec = (await session.execute(rec_stmt)).scalars().first()
            if rec:
                rec.status = "DISPATCHED_FULL_CHARGE"
                rec.amount_charged_to_customer = required_charge
                rec.pending_balance_recorded = 0.0
                rec.dispatch_option = "FULL_CHARGE_PAID"
                await session.commit()

        ack = (
            f"✅ *TRIP DISPATCH AUTHORIZED (FULL CHARGE)*\n"
            f"────────────────────\n"
            f"🚛 *Trip:* `{trip_id}`\n"
            f"💸 *Transport Charged to Customer:* ${required_charge:,.2f}\n"
            f"⚖️ *Pending Balance Added:* $0.00\n"
            f"👤 *Authorized By:* {employee.full_name if employee else 'Sales Agent'} (`+{phone}`)\n"
            f"📊 *Status:* Cleared for Vehicle Loading & Dispatch 🚛💨\n\n"
            f"Order is clear to go! Notification logged for Logistics."
        )
        buttons = [
            {"id": "btn_domain_fleet", "title": "🚛 Fleet Approval"},
            {"id": "btn_sales_menu", "title": "↩️ Main Menu"}
        ]
        await meta_api.send_button_message(
            to_phone=phone,
            body_text=ack,
            buttons=buttons,
            header_text="✅ TRIP DISPATCH AUTHORIZED"
        )
        if is_valid_phone(settings.master_group_phone):
            try:
                group_alert = (
                    f"📢 *FLEET DISPATCH (FULL CHARGE PAID)*\n"
                    f"• Trip: `{trip_id}`\n"
                    f"• Approver: {employee.full_name if employee else 'Sales'} (`+{phone}`)\n"
                    f"• Charged to Customer: ${required_charge:,.2f}\n"
                    f"• Pending Recorded: $0.00"
                )
                await meta_api.send_text_message(settings.master_group_phone, group_alert)
            except Exception as e:
                logger.warning(f"Could not alert master group of full charge dispatch: {e}")
        return True

    # 8. Shortfall Option 2: Partial Charge Initiated
    if text_lower.startswith("btn_short_part_") or (
        state and state.flow_name == "fleet_approval" and state.current_step == "awaiting_shortfall_decision" and text_lower in {"2", "2️⃣", "partial", "partial charge"}
    ):
        trip_id = ""
        required_charge = 0.0
        clean_btn_id = ""
        if state and state.current_data:
            trip_id = state.current_data.get("trip_id", "")
            required_charge = float(state.current_data.get("required_charge", 0.0))
            clean_btn_id = state.current_data.get("clean_btn_id", "")

        if not trip_id and text_lower.startswith("btn_short_part_"):
            clean_id = text_strip.replace("btn_short_part_", "").strip()
            rec_chk = (await session.execute(
                select(FleetTripApproval).where(FleetTripApproval.trip_id.ilike(f"%{clean_id}%")).order_by(FleetTripApproval.id.desc())
            )).scalars().first()
            if rec_chk:
                trip_id = rec_chk.trip_id
                required_charge = rec_chk.transport_charge
                clean_btn_id = clean_id

        await set_user_state(
            session,
            phone,
            "awaiting_partial_charge",
            {"trip_id": trip_id, "required_charge": required_charge, "clean_btn_id": clean_btn_id},
            flow_name="fleet_approval"
        )
        prompt = (
            f"💵 *PARTIAL TRANSPORT CHARGE*\n"
            f"────────────────────\n"
            f"🚛 *Trip:* `{trip_id}`\n"
            f"💸 *Required Transport Charge:* ${required_charge:,.2f}\n\n"
            f"Please enter the *amount charged to the customer*:\n"
            f"_(e.g. `50` or `75.50`)_\n\n"
            f"💡 _The remaining deficit will be added to your pending recovery balance._\n"
            f"💡 _Reply 'cancel' to exit._"
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
                "⚠️ Please enter a valid number for the amount charged (e.g. `50` or `75.50`):"
            )
            return True

        data = state.current_data or {}
        trip_id = data.get("trip_id", "")
        required_charge = float(data.get("required_charge", 0.0))
        charged_amt = round(charged_amt, 2)

        if charged_amt >= required_charge:
            charged_amt = required_charge
            remaining_pending = 0.0
        else:
            remaining_pending = round(required_charge - charged_amt, 2)
            await record_pending_ledger_entry(
                session=session,
                phone=phone,
                name=employee.full_name if employee else "Sales Colleague",
                trip_id=trip_id,
                entry_type="SHORTFALL_PARTIAL_BALANCE",
                amount=remaining_pending,
                notes=f"Partial charge ${charged_amt:,.2f} of ${required_charge:,.2f} on {trip_id}"
            )

        if trip_id:
            rec_stmt = select(FleetTripApproval).where(FleetTripApproval.trip_id == trip_id).order_by(FleetTripApproval.id.desc())
            rec = (await session.execute(rec_stmt)).scalars().first()
            if rec:
                rec.status = "DISPATCHED_PARTIAL_CHARGE"
                rec.amount_charged_to_customer = charged_amt
                rec.pending_balance_recorded = remaining_pending
                rec.dispatch_option = "PARTIAL_CHARGE"
                await session.commit()

        tot_pending = await get_sales_rep_pending_balance(session, phone)
        await clear_user_state(session, phone)

        ack = (
            f"✅ *TRIP DISPATCH AUTHORIZED (PARTIAL CHARGE)*\n"
            f"────────────────────\n"
            f"🚛 *Trip:* `{trip_id}`\n"
            f"💸 *Amount Charged to Customer:* ${charged_amt:,.2f}\n"
            f"⚖️ *Balance Added to Your Pending:* ${remaining_pending:,.2f}\n"
            f"🎯 *Your Total Pending to Recover:* *${tot_pending:,.2f}*\n"
            f"👤 *Authorized By:* {employee.full_name if employee else 'Sales Agent'} (`+{phone}`)\n"
            f"📊 *Status:* Cleared for Vehicle Loading & Dispatch 🚛💨\n\n"
            f"Order is clear to go! Remaining deficit of ${remaining_pending:,.2f} will be covered by future trip recoveries."
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
        if is_valid_phone(settings.master_group_phone):
            try:
                group_alert = (
                    f"📢 *FLEET DISPATCH (PARTIAL CHARGE)*\n"
                    f"• Trip: `{trip_id}`\n"
                    f"• Approver: {employee.full_name if employee else 'Sales'} (`+{phone}`)\n"
                    f"• Charged: ${charged_amt:,.2f}\n"
                    f"• Pending Recorded: ${remaining_pending:,.2f}"
                )
                await meta_api.send_text_message(settings.master_group_phone, group_alert)
            except Exception as e:
                logger.warning(f"Could not alert master group of partial charge dispatch: {e}")
        return True

    # 10. Shortfall Option 3: Full to Pending
    if text_lower.startswith("btn_short_none_") or (
        state and state.flow_name == "fleet_approval" and state.current_step == "awaiting_shortfall_decision" and text_lower in {"3", "3️⃣", "pending", "full to pending", "cannot charge", "none"}
    ):
        trip_id = ""
        required_charge = 0.0
        if state and state.current_data:
            trip_id = state.current_data.get("trip_id", "")
            required_charge = float(state.current_data.get("required_charge", 0.0))

        if not trip_id and text_lower.startswith("btn_short_none_"):
            clean_id = text_strip.replace("btn_short_none_", "").strip()
            rec_chk = (await session.execute(
                select(FleetTripApproval).where(FleetTripApproval.trip_id.ilike(f"%{clean_id}%")).order_by(FleetTripApproval.id.desc())
            )).scalars().first()
            if rec_chk:
                trip_id = rec_chk.trip_id
                required_charge = rec_chk.transport_charge

        await record_pending_ledger_entry(
            session=session,
            phone=phone,
            name=employee.full_name if employee else "Sales Colleague",
            trip_id=trip_id,
            entry_type="SHORTFALL_FULL_UNCHARGED",
            amount=required_charge,
            notes=f"Uncharged transport charge on trip {trip_id}"
        )

        if trip_id:
            rec_stmt = select(FleetTripApproval).where(FleetTripApproval.trip_id == trip_id).order_by(FleetTripApproval.id.desc())
            rec = (await session.execute(rec_stmt)).scalars().first()
            if rec:
                rec.status = "DISPATCHED_FULL_PENDING"
                rec.amount_charged_to_customer = 0.0
                rec.pending_balance_recorded = required_charge
                rec.dispatch_option = "FULL_TO_PENDING"
                await session.commit()

        tot_pending = await get_sales_rep_pending_balance(session, phone)
        await clear_user_state(session, phone)

        ack = (
            f"✅ *TRIP DISPATCH AUTHORIZED (FULL TO PENDING)*\n"
            f"────────────────────\n"
            f"🚛 *Trip:* `{trip_id}`\n"
            f"💸 *Amount Charged to Customer:* $0.00\n"
            f"⚖️ *Balance Added to Your Pending:* ${required_charge:,.2f}\n"
            f"🎯 *Your Total Pending to Recover:* *${tot_pending:,.2f}*\n"
            f"👤 *Authorized By:* {employee.full_name if employee else 'Sales Agent'} (`+{phone}`)\n"
            f"📊 *Status:* Cleared for Vehicle Loading & Dispatch 🚛💨\n\n"
            f"Order is clear to go! Transport charge of ${required_charge:,.2f} has been recorded to your pending balance to be covered by other trips over time."
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
        if is_valid_phone(settings.master_group_phone):
            try:
                group_alert = (
                    f"📢 *FLEET DISPATCH (FULL TO PENDING)*\n"
                    f"• Trip: `{trip_id}`\n"
                    f"• Approver: {employee.full_name if employee else 'Sales'} (`+{phone}`)\n"
                    f"• Charged: $0.00\n"
                    f"• Pending Recorded: ${required_charge:,.2f}"
                )
                await meta_api.send_text_message(settings.master_group_phone, group_alert)
            except Exception as e:
                logger.warning(f"Could not alert master group of full to pending dispatch: {e}")
        return True

    # 11. Cancel button
    if text_lower.startswith("btn_cancel_fleet_"):
        await clear_user_state(session, phone)
        await meta_api.send_text_message(phone, "❌ *Trip request cancelled.* Returning to main menu.")
        await send_sales_portal_menu(session, phone, employee)
        return True

    # 12. Handle active state 'awaiting_trip_id'
    if state and state.flow_name == "fleet_approval" and state.current_step == "awaiting_trip_id":
        if text_lower in {"cancel", "reset", "menu", "back", "exit"}:
            await clear_user_state(session, phone)
            await send_sales_portal_menu(session, phone, employee)
            return True

        trip_query = text_strip.upper().replace("TRIP-", "").strip()
        if len(trip_query) < 3:
            await meta_api.send_text_message(phone, "⚠️ Please enter a valid Trip ID (e.g. *20042026-BINDURA*):")
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
                dispatch_option="APPROVED_THRESHOLD",
                status="APPROVED_MEETS_MINIMUM",
                raw_data=result
            )
            session.add(approval_record)
            await session.commit()

            card_body = (
                f"✅ *FLEET TRIP APPROVED FOR DISPATCH*\n"
                f"────────────────────\n"
                f"🚛 *Trip:* `{trip_id}`\n"
                f"📍 *Destination:* {dest}{route_str}\n"
                f"💰 *Trip Total Sales:* ${sales_val:,.2f}\n"
                f"🎯 *Required Minimum:* ${req_min:,.2f}\n"
                f"📊 *Status:* ✅ *Passed Minimum Sales Threshold*\n"
                f"────────────────────\n"
                f"🎉 Trip meets all sales requirements! Cleared for driver dispatch and vehicle loading."
            )
            buttons = [
                {"id": f"btn_dispatch_{clean_btn_id}", "title": "🚛 Dispatch Trip"},
                {"id": "btn_sales_menu", "title": "↩️ Main Menu"}
            ]
            await set_user_state(session, phone, "awaiting_decision", {"trip_id": trip_id}, flow_name="fleet_approval")
            await meta_api.send_button_message(
                to_phone=phone,
                body_text=card_body,
                buttons=buttons,
                header_text="🚛 TRIP VERIFICATION PASSED"
            )
        else:
            # Shortfall detected -> Save record & Send 3 Options
            # CONFIDENTIALITY: Strictly NO '4%' mention anywhere!
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
                f"📋 *FLEET TRIP VERIFICATION*\n"
                f"────────────────────\n"
                f"🚛 *Trip:* `{trip_id}`\n"
                f"📍 *Destination:* {dest}{route_str}\n"
                f"💰 *Trip Total Sales:* ${sales_val:,.2f}\n"
                f"🎯 *Required Minimum:* ${req_min:,.2f}\n\n"
                f"⚠️ *SHORTFALL DETECTED:* ${shortfall:,.2f}\n"
                f"💸 *Transport Charge:* *${transport_charge:,.2f}*\n"
                f"────────────────────\n"
                f"⚠️ *Action Required:* Minimum sales threshold not reached.\n"
                f"Please select a transport charge resolution for dispatch:\n\n"
                f"1️⃣ *Full Charge:* Customer paid ${transport_charge:,.2f} in full. Order clear to go.\n"
                f"2️⃣ *Partial Charge:* Customer paid part; remainder recorded to your pending balance.\n"
                f"3️⃣ *Full to Pending:* Uncharged; full ${transport_charge:,.2f} recorded to your pending balance."
            )
            buttons = [
                {"id": f"btn_short_full_{clean_btn_id}", "title": "1️⃣ Full Charge"},
                {"id": f"btn_short_part_{clean_btn_id}", "title": "2️⃣ Partial Charge"},
                {"id": f"btn_short_none_{clean_btn_id}", "title": "3️⃣ Full to Pending"}
            ]
            await set_user_state(
                session,
                phone,
                "awaiting_shortfall_decision",
                {"trip_id": trip_id, "required_charge": transport_charge, "clean_btn_id": clean_btn_id},
                flow_name="fleet_approval"
            )
            await meta_api.send_button_message(
                to_phone=phone,
                body_text=card_body,
                buttons=buttons,
                header_text="⚠️ SHORTFALL - SELECT ACTION"
            )
        return True

    return False

