import logging
import re
from typing import Optional, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import Employee, Department, ConversationState, FleetTripApproval
from app.state_manager import set_user_state, clear_user_state, get_user_state
from app.meta_api import meta_api
from app.services.trip_verification_service import trip_verification_service

logger = logging.getLogger("fleet_approval_handler")

# In-memory role override cache for instant WhatsApp one-word role toggling
# Allows +919265368695 to switch live between "SALES" and "MASTER_ADMIN" via chat
SESSION_ROLE_OVERRIDES: Dict[str, str] = {}


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
            "When you message the bot, you will receive exactly 2 buttons:\n"
            "• *[ 💻 IT Support ]*\n"
            "• *[ 🚛 Fleet Approval ]*\n\n"
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
    Presents the salesperson 2-button menu:
    1. [ 💻 IT Support ] (Exact label as standard employees)
    2. [ 🚛 Fleet Approval ]
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
        {"id": "btn_domain_fleet", "title": "🚛 Fleet Approval"}
    ]
    await set_user_state(session, phone, "select_service", {}, flow_name="sales_portal")
    await meta_api.send_button_message(
        to_phone=phone,
        body_text=body,
        buttons=buttons,
        header_text=header,
        footer_text=footer
    )


async def handle_fleet_approval_flow(
    session: AsyncSession,
    phone: str,
    employee: Optional[Employee],
    message_text: str,
    state: Optional[ConversationState]
) -> bool:
    """
    Handles WhatsApp message flow for Fleet Approval (Trip verification, shortfall calculation, dispatch approval).
    Returns True if handled, False otherwise.
    """
    text_strip = message_text.strip()
    text_lower = text_strip.lower()

    # Step 1: User taps [ 🚛 Fleet Approval ] button or types command
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

    # Step 2: Handle Accept / Cancel dispatch buttons
    if text_lower.startswith(("btn_accept_fleet_", "btn_dispatch_")):
        trip_id = text_strip.replace("btn_accept_fleet_", "").replace("btn_dispatch_", "").strip()
        await clear_user_state(session, phone)

        # Update latest record in fleet_trip_approvals
        rec_stmt = (
            select(FleetTripApproval)
            .where(FleetTripApproval.trip_id == trip_id)
            .order_by(FleetTripApproval.id.desc())
        )
        rec = (await session.execute(rec_stmt)).scalars().first()
        if rec:
            rec.status = "DISPATCHED"
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
        # Notify Master Group if configured
        if settings.master_group_phone:
            try:
                group_alert = (
                    f"📢 *NEW FLEET DISPATCH APPROVED*\n"
                    f"• Trip: `{trip_id}`\n"
                    f"• Approver: {employee.full_name if employee else 'Sales'} (`+{phone}`)\n"
                    f"• Time: Done via WhatsApp Portal"
                )
                await meta_api.send_text_message(settings.master_group_phone, group_alert)
            except Exception as e:
                logger.warning(f"Could not alert master group of fleet approval: {e}")
        return True

    if text_lower.startswith("btn_cancel_fleet_"):
        await clear_user_state(session, phone)
        await meta_api.send_text_message(phone, "❌ *Trip request cancelled.* Returning to main menu.")
        await send_sales_portal_menu(session, phone, employee)
        return True

    # Step 3: Handle active state 'awaiting_trip_id'
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

        clean_btn_id = re.sub(r"[^\w-]", "", trip_id)[:50]

        # 1. Save record in database for audit and future dashboard visualization
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
            has_shortfall=not is_approved,
            status="APPROVED_MEETS_MINIMUM" if is_approved else "SHORTFALL_LOGGED",
            raw_data=result
        )
        session.add(approval_record)
        await session.commit()

        if is_approved:
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
            # When shortfall is detected: NO BUTTONS!
            # Transport charge & shortfall are stored in DB and presented purely as information.
            card_body = (
                f"📋 *FLEET TRIP VERIFICATION*\n"
                f"────────────────────\n"
                f"🚛 *Trip:* `{trip_id}`\n"
                f"📍 *Destination:* {dest}{route_str}\n"
                f"💰 *Trip Total Sales:* ${sales_val:,.2f}\n"
                f"🎯 *Required Minimum:* ${req_min:,.2f}\n\n"
                f"⚠️ *SHORTFALL DETECTED:* ${shortfall:,.2f}\n"
                f"💸 *Transport Charge (4%):* *${transport_charge:,.2f}*\n"
                f"────────────────────\n"
                f"⚠️ *Status:* Recorded in Fleet System\n\n"
                f"This trip is below the minimum required sales threshold.\n"
                f"The transport charge of *${transport_charge:,.2f}* has been logged and recorded for management review.\n\n"
                f"💡 _Reply 'hi' or 'menu' to return to the main menu._"
            )
            await clear_user_state(session, phone)
            await meta_api.send_text_message(phone, card_body)
        return True

    return False
