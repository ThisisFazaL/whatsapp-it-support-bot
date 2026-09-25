import logging
import re
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import (
    FleetTripRequest,
    get_fleet_trip_request_by_id
)
from app.state_manager import set_user_state, clear_user_state, get_user_state, normalize_phone_number
from app.meta_api import meta_api

logger = logging.getLogger("zayn_accounts_handler")


def clean_phone(phone: Optional[str]) -> str:
    return normalize_phone_number(str(phone or ""))



async def notify_zayn_allowance_approval(session: AsyncSession, trip_id: str):
    """
    Sends the official allowance approval prompt to Zayn.
    Template conforms exactly to requested layout.
    """
    trip = await get_fleet_trip_request_by_id(session, trip_id)
    if not trip:
        return

    from app.handlers.fleet_approval_handler import get_solo_test_mode
    is_solo = get_solo_test_mode()
    header = "ALLOWANCE APPROVAL NEEDED"
    tag = "🎭 *[SOLO TEST: SIMULATING ZAYN]*\n" if is_solo else ""
    body = (
        f"{tag}ALLOWANCE APPROVAL NEEDED\n"
        "────────────────────\n"
        f"Company: {trip.company_name}\n"
        f"Trip: {trip.trip_id} | Route: {trip.route or trip.destination_city}\n"
        f"Driver: {trip.driver_name} | Truck: {trip.truck_plate}\n"
        f"Crew: {trip.crew_count} people | Meals: {trip.meal_count} | Tolls: {trip.toll_gates_count}\n"
        "────────────────────\n"
        f"Toll cost: ${trip.toll_cost:,.2f}\n"
        f"Food ($2 x {trip.crew_count} x {trip.meal_count}): ${trip.food_allowance:,.2f}\n"
        "────────────────────\n"
        f"Total allowance: ${trip.total_allowance:,.2f}\n"
        "Please approve or recalculate:"
    )
    buttons = [
        {"id": f"flt_zayn_app_{trip.trip_id}", "title": "Approve"},
        {"id": f"flt_zayn_recalc_{trip.trip_id}", "title": "Recalculate"}
    ]

    recipients = {clean_phone(settings.master_admin_phone)} if is_solo else {clean_phone(settings.zayn_phone)}
    if not is_solo and getattr(settings, "test_user_role", "").upper() == "ZAYN":
        recipients.add(clean_phone(settings.master_admin_phone))


    for r in recipients:
        if r:
            await meta_api.send_button_message(
                to_phone=r,
                body_text=body,
                buttons=buttons,
                header_text=header
            )
    logger.info(f"Delivered Zayn allowance approval prompt for {trip_id} to Zayn ({settings.zayn_phone})")


async def notify_accounts_allowance_transfer(session: AsyncSession, trip_id: str):
    """Alerts Accounts department to execute the allowance bank transfer."""
    trip = await get_fleet_trip_request_by_id(session, trip_id)
    if not trip:
        return

    from app.handlers.fleet_approval_handler import get_solo_test_mode
    is_solo = get_solo_test_mode()
    header = "ALLOWANCE APPROVED"
    tag = "🎭 *[SOLO TEST: SIMULATING ACCOUNTS]*\n" if is_solo else ""
    body = (
        f"{tag}ALLOWANCE APPROVED\n"
        "────────────────────\n"
        f"Trip: {trip.trip_id}\n"
        f"Company: {trip.company_name}\n"
        f"Driver: {trip.driver_name} (+{trip.driver_phone})\n"
        f"Truck: {trip.truck_plate}\n"
        f"Total Allowance: ${trip.total_allowance:,.2f}\n"
        f"(Tolls: ${trip.toll_cost:,.2f} | Food: ${trip.food_allowance:,.2f})\n"
        "────────────────────\n"
        "Please handle money transfer and confirm below:"
    )
    buttons = [
        {"id": f"flt_acc_done_{trip.trip_id}", "title": "Transfer Done"}
    ]

    account_phones = [clean_phone(settings.master_admin_phone)] if is_solo else [clean_phone(p) for p in settings.accounts_phones if clean_phone(p)]

    for ap in account_phones:
        await meta_api.send_button_message(
            to_phone=ap,
            body_text=body,
            buttons=buttons,
            header_text=header
        )
    logger.info(f"Delivered Accounts transfer alert for {trip_id} to {account_phones}")


async def handle_zayn_accounts_interaction(
    session: AsyncSession,
    phone: str,
    message_text: str,
    state: Optional[Any]
) -> bool:
    """
    Handles all interactions for Zayn (Approver) and Accounts (Transfer) in Stage 4.
    Returns True if handled, False otherwise.
    """
    clean_p = clean_phone(phone)
    text_strip = message_text.strip()
    text_lower = text_strip.lower()

    # 1. Zayn clicks [Approve]
    if text_lower.startswith("flt_zayn_app_"):
        trip_id = text_strip.replace("flt_zayn_app_", "").strip()
        trip = await get_fleet_trip_request_by_id(session, trip_id)
        if not trip:
            await meta_api.send_text_message(clean_p, f"⚠️ Trip {trip_id} not found.")
            return True

        trip.allowance_status = "APPROVED"
        trip.allowance_approved_by = "Zayn"
        await session.commit()
        await clear_user_state(session, clean_p)

        ack = (
            f"✅ *ALLOWANCE APPROVED: {trip_id}*\n"
            "────────────────────\n"
            f"Approved amount: ${trip.total_allowance:,.2f}\n"
            "Notification forwarded to Accounts for money transfer!"
        )
        await meta_api.send_text_message(clean_p, ack)

        # Notify Accounts
        await notify_accounts_allowance_transfer(session, trip_id)
        return True

    # 2. Zayn clicks [Recalculate]
    if text_lower.startswith("flt_zayn_recalc_"):
        trip_id = text_strip.replace("flt_zayn_recalc_", "").strip()
        await set_user_state(
            session,
            clean_p,
            current_step="awaiting_recalc_notes",
            current_data={"trip_id": trip_id},
            flow_name="fleet_zayn"
        )
        prompt = (
            f"📝 *RECALCULATE ALLOWANCE: {trip_id}*\n"
            "────────────────────\n"
            "Please enter recalculation instructions/notes for Edward:\n"
            "_(e.g. Reduce tolls to 2 or check meal count)_"
        )
        await meta_api.send_text_message(clean_p, prompt)
        return True

    # 3. Zayn enters recalculation notes
    if state and state.flow_name == "fleet_zayn" and state.current_step == "awaiting_recalc_notes":
        if text_lower in {"cancel", "reset", "menu", "back", "exit"}:
            await clear_user_state(session, clean_p)
            await meta_api.send_text_message(clean_p, "Recalculation request cancelled.")
            return True

        data = state.current_data or {}
        trip_id = data.get("trip_id", "")
        trip = await get_fleet_trip_request_by_id(session, trip_id)

        notes = text_strip
        if trip:
            trip.allowance_status = "RECALCULATE"
            trip.status = "PENDING_ASSIGNMENT"
            await session.commit()

        await clear_user_state(session, clean_p)
        await meta_api.send_text_message(
            clean_p,
            f"✅ Recalculation request logged for Trip {trip_id}. Edward has been notified."
        )

        # Alert Edward
        edw_phone = clean_phone(settings.edward_phone)
        edw_alert = (
            f"⚠️ *ALLOWANCE RECALCULATION NEEDED: {trip_id}*\n"
            "────────────────────\n"
            f"Notes from Zayn:\n\"{notes}\"\n"
            "────────────────────\n"
            "Please update the allocation details for this trip:"
        )
        buttons = [
            {"id": f"flt_edw_alloc_{trip_id}", "title": "Allocate Trip"}
        ]
        await meta_api.send_button_message(
            to_phone=edw_phone,
            body_text=edw_alert,
            buttons=buttons,
            header_text="RECALCULATION"
        )
        return True

    # 4. Accounts clicks [Transfer Done]
    if text_lower.startswith("flt_acc_done_"):
        trip_id = text_strip.replace("flt_acc_done_", "").strip()
        trip = await get_fleet_trip_request_by_id(session, trip_id)
        if not trip:
            await meta_api.send_text_message(clean_p, f"⚠️ Trip {trip_id} not found.")
            return True

        trip.allowance_status = "TRANSFERRED"
        await session.commit()
        await clear_user_state(session, clean_p)

        ack = (
            f"✅ *TRANSFER CONFIRMED: {trip_id}*\n"
            "────────────────────\n"
            f"Allowance: ${trip.total_allowance:,.2f}\n"
            f"Driver {trip.driver_name} (+{trip.driver_phone}) has been notified to set departure time."
        )
        await meta_api.send_text_message(clean_p, ack)

        # Notify Driver for departure time
        from app.handlers.fleet_approval_handler import get_solo_test_mode
        is_solo = get_solo_test_mode()
        drv_p = clean_phone(settings.master_admin_phone if is_solo else (trip.driver_phone or settings.master_admin_phone))
        tag = "🎭 *[SOLO TEST: SIMULATING DRIVER]*\n" if is_solo else ""
        drv_prompt = (
            f"{tag}💵 *ALLOWANCE TRANSFERRED: {trip.trip_id}*\n"
            "────────────────────\n"
            f"Truck: {trip.truck_plate}\n"
            f"Total Allowance: ${trip.total_allowance:,.2f}\n"
            "────────────────────\n"
            "Please enter your scheduled departure time:\n"
            "_(e.g. 06:30 AM or 07:00 AM)_"
        )
        # Always set user state for actual driver_phone
        if trip.driver_phone:
            await set_user_state(
                session,
                clean_phone(trip.driver_phone),
                current_step="awaiting_departure_time",
                current_data={"trip_id": trip.trip_id},
                flow_name="fleet_driver"
            )
        # In solo mode, also set user state for master admin phone so single tester can reply directly
        if is_solo and drv_p != clean_phone(trip.driver_phone):
            await set_user_state(
                session,
                drv_p,
                current_step="awaiting_departure_time",
                current_data={"trip_id": trip.trip_id},
                flow_name="fleet_driver"
            )
        await meta_api.send_text_message(drv_p, drv_prompt)
        return True

    return False
