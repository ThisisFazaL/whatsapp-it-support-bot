import logging
import re
import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import (
    FleetTripRequest,
    get_fleet_trip_request_by_id,
    get_trip_reconciliation_summary,
    record_driver_pending_entry
)
from app.state_manager import set_user_state, clear_user_state, get_user_state
from app.meta_api import meta_api

logger = logging.getLogger("logistics_manager_handler")


def clean_phone(phone: Optional[str]) -> str:
    if not phone:
        return ""
    return re.sub(r"[^\d]", "", str(phone))


async def notify_logistics_manager_adjudication(session: AsyncSession, trip_id: str):
    """
    Sends adjudication / final sign-off card to Logistics Manager.
    """
    summary = await get_trip_reconciliation_summary(session, trip_id)
    trip: Optional[FleetTripRequest] = summary.get("trip")
    if not trip:
        return

    mgr_phone = clean_phone(settings.logistics_manager_phone)

    if abs(trip.discrepancy_amount) > 0.01:
        header = "TRIP ADJUDICATION"
        body = (
            "TRIP ADJUDICATION NEEDED\n"
            "────────────────────\n"
            f"Company: {trip.company_name}\n"
            f"Trip: {trip.trip_id} | Route: {trip.route or trip.destination_city}\n"
            f"Driver: {trip.driver_name} | Truck: {trip.truck_plate}\n"
            "────────────────────\n"
            f"Discrepancy: ${trip.discrepancy_amount:,.2f}\n"
            f"Reason: {trip.discrepancy_reason or 'No notes provided'}\n"
            "────────────────────\n"
            "Please approve or reject reimbursement / deduction:"
        )
        buttons = [
            {"id": f"flt_mgr_app_{trip.trip_id}", "title": "Approve"},
            {"id": f"flt_mgr_rej_{trip.trip_id}", "title": "Reject"}
        ]
    else:
        header = "TRIP CLOSURE"
        body = (
            "TRIP READY FOR CLOSURE\n"
            "────────────────────\n"
            f"Company: {trip.company_name}\n"
            f"Trip: {trip.trip_id} | Route: {trip.route or trip.destination_city}\n"
            f"Driver: {trip.driver_name} | Truck: {trip.truck_plate}\n"
            f"Total Delivery Charges: ${summary.get('total_collected', 0.0):,.2f}\n"
            "Physical balancing settled with zero discrepancy.\n"
            "────────────────────\n"
            "Please authorize final trip closure:"
        )
        buttons = [
            {"id": f"flt_mgr_close_{trip.trip_id}", "title": "Close Trip"}
        ]

    recipients = {mgr_phone}
    if getattr(settings, "test_user_role", "").upper() == "LOGISTICS_MANAGER":
        recipients.add(clean_phone(settings.master_admin_phone))

    for r in recipients:
        if r:
            await meta_api.send_button_message(
                to_phone=r,
                body_text=body,
                buttons=buttons,
                header_text=header
            )
    logger.info(f"Delivered Stage 7 adjudication card for {trip_id} to Logistics Manager ({mgr_phone})")


async def broadcast_confidential_trip_closed(session: AsyncSession, trip_id: str):
    """
    Broadcasts the final TRIP CLOSED notification.
    CRITICAL SECURITY RULE:
    Sales Total is STRICTLY HIDDEN from:
    1. Driver
    2. Sales Rep
    3. Edward
    4. Sales Admin
    """
    summary = await get_trip_reconciliation_summary(session, trip_id)
    trip: Optional[FleetTripRequest] = summary.get("trip")
    if not trip:
        return

    trip.status = "CLOSED"
    trip.closed_at = datetime.datetime.utcnow()
    await session.commit()

    total_collected = summary.get("total_collected", 0.0)
    cash_collected = summary.get("cash_collected", 0.0)
    bank_collected = summary.get("bank_collected", 0.0)
    total_emergencies = summary.get("total_emergencies", 0.0)
    total_allowance = summary.get("total_allowance", 0.0)

    # Confidential broadcast notice (No Sales Total!)
    operational_msg = (
        "🏁 *TRIP CLOSED*\n"
        "────────────────────\n"
        f"🏢 *Company:* {trip.company_name}\n"
        f"🚛 *Trip:* `{trip.trip_id}` | *Route:* {trip.route or trip.destination_city}\n"
        f"👤 *Driver:* {trip.driver_name} | *Truck:* {trip.truck_plate}\n"
        "────────────────────\n"
        f"💰 *Transport Collected:* ${total_collected:,.2f}\n"
        f"💵 *Cash:* ${cash_collected:,.2f} | 💳 *Bank:* ${bank_collected:,.2f}\n"
        f"⚠️ *Emergency Expenses:* ${total_emergencies:,.2f}\n"
        f"🍱 *Allowance Reconciled:* ${total_allowance:,.2f}\n"
        f"⚖️ *Balancing Status:* Settled ({trip.reimbursement_status})\n"
        "────────────────────\n"
        "✅ Trip operations successfully closed."
    )

    operational_recipients = set()
    if trip.driver_phone:
        operational_recipients.add(clean_phone(trip.driver_phone))
    if trip.salesperson_phone:
        operational_recipients.add(clean_phone(trip.salesperson_phone))
    if settings.edward_phone:
        operational_recipients.add(clean_phone(settings.edward_phone))
    if trip.sales_admin_phone:
        operational_recipients.add(clean_phone(trip.sales_admin_phone))
    else:
        operational_recipients.add(clean_phone(settings.sales_admin_tg_phone))

    for rec_phone in operational_recipients:
        if rec_phone:
            try:
                await meta_api.send_text_message(rec_phone, operational_msg)
            except Exception as e:
                logger.warning(f"Could not deliver closed broadcast to {rec_phone}: {e}")

    # Executive confidential report to Master / Fleet Admin (Sujit) with full metrics
    exec_msg = (
        "👑 *EXECUTIVE AUDIT: TRIP CLOSED*\n"
        "────────────────────\n"
        f"Trip: `{trip.trip_id}` | Company: {trip.company_name}\n"
        f"Sales Total (Confidential): ${trip.trip_sales_value:,.2f}\n"
        f"Transport Collected: ${total_collected:,.2f}\n"
        f"Discrepancy: ${trip.discrepancy_amount:,.2f} ({trip.reimbursement_status})\n"
        "────────────────────\n"
        "Operational staff notified with sales total concealed."
    )
    admin_phones = {clean_phone(settings.fleet_admin_phone), clean_phone(settings.master_admin_phone)}
    for ap in admin_phones:
        if ap:
            try:
                await meta_api.send_text_message(ap, exec_msg)
            except Exception as e:
                logger.warning(f"Could not deliver executive closed report to {ap}: {e}")


async def handle_logistics_manager_interaction(
    session: AsyncSession,
    phone: str,
    message_text: str,
    state: Optional[Any]
) -> bool:
    """
    Handles all interactions for Logistics Manager in Stage 7.
    Returns True if handled, False otherwise.
    """
    clean_p = clean_phone(phone)
    text_strip = message_text.strip()
    text_lower = text_strip.lower()

    # 1. Close Trip (No discrepancy)
    if text_lower.startswith("flt_mgr_close_"):
        trip_id = text_strip.replace("flt_mgr_close_", "").strip()
        trip = await get_fleet_trip_request_by_id(session, trip_id)
        if not trip:
            await meta_api.send_text_message(clean_p, f"⚠️ Trip {trip_id} not found.")
            return True

        trip.reimbursement_status = "NONE"
        await session.commit()
        await clear_user_state(session, clean_p)

        await meta_api.send_text_message(
            clean_p,
            f"✅ Trip {trip_id} officially closed. Broadcast sent to driver, sales rep, Edward, and sales admin."
        )
        await broadcast_confidential_trip_closed(session, trip_id)
        return True

    # 2. Approve Discrepancy Reimbursement
    if text_lower.startswith("flt_mgr_app_"):
        trip_id = text_strip.replace("flt_mgr_app_", "").strip()
        trip = await get_fleet_trip_request_by_id(session, trip_id)
        if not trip:
            await meta_api.send_text_message(clean_p, f"⚠️ Trip {trip_id} not found.")
            return True

        trip.reimbursement_status = "APPROVED"
        await session.commit()
        await clear_user_state(session, clean_p)

        await meta_api.send_text_message(
            clean_p,
            f"✅ Discrepancy reimbursement approved for Trip {trip_id}. Trip closed."
        )
        await broadcast_confidential_trip_closed(session, trip_id)
        return True

    # 3. Reject Discrepancy (Deduct from Driver)
    if text_lower.startswith("flt_mgr_rej_"):
        trip_id = text_strip.replace("flt_mgr_rej_", "").strip()
        trip = await get_fleet_trip_request_by_id(session, trip_id)
        if not trip:
            await meta_api.send_text_message(clean_p, f"⚠️ Trip {trip_id} not found.")
            return True

        trip.reimbursement_status = "REJECTED"
        await session.commit()

        # Add deficit to Driver Pending Ledger if short
        if trip.discrepancy_amount > 0 and trip.driver_phone:
            await record_driver_pending_entry(
                session=session,
                driver_phone=trip.driver_phone,
                driver_name=trip.driver_name,
                trip_id=trip.trip_id,
                amount=trip.discrepancy_amount,
                reason=f"Rejected discrepancy on trip {trip.trip_id}: {trip.discrepancy_reason}"
            )

        await clear_user_state(session, clean_p)
        await meta_api.send_text_message(
            clean_p,
            f"❌ Discrepancy rejected for Trip {trip_id}. Deficit logged in driver pending ledger. Trip closed."
        )
        await broadcast_confidential_trip_closed(session, trip_id)
        return True

    return False
