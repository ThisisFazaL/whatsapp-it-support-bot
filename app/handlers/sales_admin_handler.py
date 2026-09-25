import logging
import re
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import (
    FleetTripRequest,
    get_fleet_trip_request_by_id,
    get_trip_reconciliation_summary
)
from app.state_manager import set_user_state, clear_user_state, get_user_state, normalize_phone_number
from app.meta_api import meta_api

logger = logging.getLogger("sales_admin_handler")


def clean_phone(phone: Optional[str]) -> str:
    return normalize_phone_number(str(phone or ""))



def get_sales_admin_phone_for_company(company_name: str) -> str:
    c_lower = (company_name or "").lower()
    if "lg" in c_lower:
        return clean_phone(settings.sales_admin_lg_phone)
    elif "kreckle" in c_lower:
        return clean_phone(settings.sales_admin_kreckle_phone)
    else:
        return clean_phone(settings.sales_admin_tg_phone)


async def notify_sales_admin_balancing_session(session: AsyncSession, trip_id: str):
    """
    Summons the assigned company Sales Admin for physical balancing session.
    Presents complete customer reconciliation card.
    """
    summary = await get_trip_reconciliation_summary(session, trip_id)
    trip: Optional[FleetTripRequest] = summary.get("trip")
    if not trip:
        return

    admin_phone = get_sales_admin_phone_for_company(trip.company_name)
    schedules = summary.get("schedules", [])
    emergencies = summary.get("emergencies", [])

    sched_lines = []
    for s in schedules:
        sched_lines.append(
            f"• {s.customer_id}: Exp ${s.expected_charge:,.2f} | Col ${s.collected_charge:,.2f} ({s.payment_method}) [{s.status}]"
        )
    sched_text = "\n".join(sched_lines) if sched_lines else "• No customer schedule records."

    emg_lines = []
    for e in emergencies:
        emg_lines.append(f"• {e.charge_type}: ${e.amount:,.2f} ({e.description or ''})")
    emg_text = "\n".join(emg_lines) if emg_lines else "• None"

    header = "BALANCING SESSION"
    body = (
        "PHYSICAL BALANCING SESSION\n"
        "────────────────────\n"
        f"Company: {trip.company_name}\n"
        f"Trip: {trip.trip_id} | Route: {trip.route or trip.destination_city}\n"
        f"Driver: {trip.driver_name} | Truck: {trip.truck_plate}\n"
        "────────────────────\n"
        f"Customer Collections:\n{sched_text}\n"
        "────────────────────\n"
        f"Emergency Expenses:\n{emg_text}\n"
        "────────────────────\n"
        f"Allowance Paid: ${summary.get('total_allowance', 0.0):,.2f}\n"
        f"Delivery Charges Collected: ${summary.get('total_collected', 0.0):,.2f}\n"
        f"💵 Physical Cash Due: ${summary.get('cash_collected', 0.0):,.2f}\n"
        f"💳 Bank/EcoCash: ${summary.get('bank_collected', 0.0):,.2f}\n"
        "────────────────────\n"
        "Verify physical cash and select status:"
    )
    buttons = [
        {"id": f"flt_adm_bal_{trip.trip_id}", "title": "Balanced"},
        {"id": f"flt_adm_unbal_{trip.trip_id}", "title": "Not Balancing"}
    ]

    recipients = {admin_phone}
    if getattr(settings, "test_user_role", "").upper() == "SALES_ADMIN":
        recipients.add(clean_phone(settings.master_admin_phone))

    for r in recipients:
        if r:
            await meta_api.send_button_message(
                to_phone=r,
                body_text=body,
                buttons=buttons,
                header_text=header
            )
    logger.info(f"Delivered Stage 6 balancing card for {trip_id} to Sales Admin ({admin_phone})")


async def handle_sales_admin_interaction(
    session: AsyncSession,
    phone: str,
    message_text: str,
    state: Optional[Any]
) -> bool:
    """
    Handles all interactions for Sales Admin in Stage 6.
    Returns True if handled, False otherwise.
    """
    clean_p = clean_phone(phone)
    text_strip = message_text.strip()
    text_lower = text_strip.lower()

    # 0. Manual trigger: balance <trip_id> or settle <trip_id>
    if text_lower.startswith(("balance ", "settle ", "reconcile ")):
        parts = text_strip.split(maxsplit=1)
        if len(parts) > 1:
            req_trip_id = parts[1].strip().upper()
            trip = await get_fleet_trip_request_by_id(session, req_trip_id)
            if trip:
                await notify_sales_admin_balancing_session(session, trip.trip_id)
                return True
            else:
                await meta_api.send_text_message(clean_p, f"⚠️ Trip '{req_trip_id}' not found.")
                return True

    # 1. Sales Admin clicks [Balanced]
    if text_lower.startswith("flt_adm_bal_"):
        trip_id = text_strip.replace("flt_adm_bal_", "").strip()
        trip = await get_fleet_trip_request_by_id(session, trip_id)
        if not trip:
            await meta_api.send_text_message(clean_p, f"⚠️ Trip {trip_id} not found.")
            return True

        trip.status = "BALANCED"
        trip.discrepancy_amount = 0.0
        trip.discrepancy_reason = "Balanced in full"
        await session.commit()
        await clear_user_state(session, clean_p)

        ack = (
            f"✅ *BALANCING VERIFIED: {trip_id}*\n"
            "────────────────────\n"
            "Physical cash confirmed. Forwarded to Logistics Manager for final trip closure."
        )
        await meta_api.send_text_message(clean_p, ack)

        # Notify Logistics Manager for Stage 7 final closure
        from app.handlers.logistics_manager_handler import notify_logistics_manager_adjudication
        await notify_logistics_manager_adjudication(session, trip_id)
        return True

    # 2. Sales Admin clicks [Not Balancing]
    if text_lower.startswith("flt_adm_unbal_"):
        trip_id = text_strip.replace("flt_adm_unbal_", "").strip()
        await set_user_state(
            session,
            clean_p,
            current_step="awaiting_discrepancy_amount",
            current_data={"trip_id": trip_id},
            flow_name="fleet_sales_admin"
        )
        prompt = (
            f"⚖️ *DISCREPANCY RECORD: {trip_id}*\n"
            "────────────────────\n"
            "Please enter the discrepancy amount in USD:\n"
            "_(e.g. 20.00 if cash is short, or -10.00 if surplus)_"
        )
        await meta_api.send_text_message(clean_p, prompt)
        return True

    # 3. Active state handling for Sales Admin
    if state and state.flow_name == "fleet_sales_admin":
        data = state.current_data or {}
        trip_id = data.get("trip_id", "")
        trip = await get_fleet_trip_request_by_id(session, trip_id)

        if state.current_step == "awaiting_discrepancy_amount":
            clean_val = re.sub(r"[^\d.-]", "", text_strip)
            try:
                disc_amt = float(clean_val)
            except ValueError:
                await meta_api.send_text_message(clean_p, "⚠️ Please enter a valid number (e.g. 20.00):")
                return True

            data["discrepancy_amount"] = disc_amt
            await set_user_state(session, clean_p, "awaiting_discrepancy_reason", data, flow_name="fleet_sales_admin")
            prompt = (
                f"📝 *DISCREPANCY REASON: {trip_id}*\n"
                f"Amount: ${disc_amt:,.2f}\n"
                "────────────────────\n"
                "Please enter the reason for this discrepancy:\n"
                "_(e.g. Customer CUST-102 paid $20 less than expected)_"
            )
            await meta_api.send_text_message(clean_p, prompt)
            return True

        if state.current_step == "awaiting_discrepancy_reason":
            reason = text_strip
            disc_amt = float(data.get("discrepancy_amount", 0.0))

            if trip:
                trip.status = "BALANCED"  # Physical session finished with variance
                trip.discrepancy_amount = disc_amt
                trip.discrepancy_reason = reason
                await session.commit()

            await clear_user_state(session, clean_p)
            ack = (
                f"⚠️ *DISCREPANCY LOGGED: {trip_id}*\n"
                "────────────────────\n"
                f"Amount: ${disc_amt:,.2f}\n"
                f"Reason: {reason}\n"
                "────────────────────\n"
                "Forwarded to Logistics Manager for adjudication and sign-off."
            )
            await meta_api.send_text_message(clean_p, ack)

            # Notify Logistics Manager for adjudication
            from app.handlers.logistics_manager_handler import notify_logistics_manager_adjudication
            await notify_logistics_manager_adjudication(session, trip_id)
            return True

    return False
