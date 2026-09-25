import logging
import re
import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import (
    FleetTripRequest,
    FleetCustomerSchedule,
    get_fleet_trip_request_by_id,
    get_active_trip_for_driver,
    record_driver_delivery_payment,
    record_emergency_expense
)
from app.state_manager import set_user_state, clear_user_state, get_user_state, normalize_phone_number
from app.meta_api import meta_api

logger = logging.getLogger("driver_handler")


def clean_phone(phone: Optional[str]) -> str:
    return normalize_phone_number(str(phone or ""))



async def send_driver_transit_menu(session: AsyncSession, phone: str, trip_id: str):
    """Presents the 3 live transit buttons to Driver (NO emojis, <= 20 chars)."""
    header = "TRIP IN TRANSIT"
    body = (
        f"🚛 *TRIP IN TRANSIT: {trip_id}*\n"
        "────────────────────\n"
        "Live location tracking is active.\n"
        "Please select an option below:"
    )
    buttons = [
        {"id": f"flt_drv_deliv_{trip_id}", "title": "Delivery Charges"},
        {"id": f"flt_drv_emerg_{trip_id}", "title": "Emergency Charges"},
        {"id": f"flt_drv_ret_{trip_id}", "title": "I am Returning"}
    ]
    await set_user_state(
        session,
        phone,
        current_step="in_transit",
        current_data={"trip_id": trip_id},
        flow_name="fleet_driver"
    )
    await meta_api.send_button_message(
        to_phone=phone,
        body_text=body,
        buttons=buttons,
        header_text=header
    )


async def send_driver_returning_menu(session: AsyncSession, phone: str, trip_id: str):
    """Presents the 2 returning buttons to Driver (NO emojis, <= 20 chars)."""
    header = "RETURNING TO BASE"
    body = (
        f"🚛 *RETURNING TO BASE: {trip_id}*\n"
        "────────────────────\n"
        "Live tracking has been turned off.\n"
        "When you arrive at the company depot, tap 'I Have Returned':"
    )
    buttons = [
        {"id": f"flt_drv_emerg_{trip_id}", "title": "Emergency Charges"},
        {"id": f"flt_drv_returned_{trip_id}", "title": "I Have Returned"}
    ]
    await set_user_state(
        session,
        phone,
        current_step="returning_to_base",
        current_data={"trip_id": trip_id},
        flow_name="fleet_driver"
    )
    await meta_api.send_button_message(
        to_phone=phone,
        body_text=body,
        buttons=buttons,
        header_text=header
    )


async def handle_driver_interaction(
    session: AsyncSession,
    phone: str,
    message_text: str,
    state: Optional[Any]
) -> bool:
    """
    Handles all interactions for Driver (Stage 5).
    Returns True if handled, False otherwise.
    """
    clean_p = clean_phone(phone)
    text_strip = message_text.strip()
    text_lower = text_strip.lower()

    # 1. Driver clicks [Trip Started]
    if text_lower.startswith("flt_drv_start_"):
        trip_id = text_strip.replace("flt_drv_start_", "").strip()
        trip = await get_fleet_trip_request_by_id(session, trip_id)
        if not trip:
            await meta_api.send_text_message(clean_p, f"⚠️ Trip {trip_id} not found.")
            return True

        trip.status = "ACTIVE"
        trip.is_live_location_active = True
        trip.departed_at = datetime.datetime.utcnow()
        await session.commit()

        # Notify perspective Sales Rep
        if trip.salesperson_phone:
            rep_phone = clean_phone(trip.salesperson_phone)
            rep_alert = (
                f"🚛 *TRIP STARTED: {trip.trip_id}*\n"
                "────────────────────\n"
                f"Driver: {trip.driver_name}\n"
                f"Truck: {trip.truck_plate}\n"
                f"Departure Time: {trip.departure_time or 'Just now'}\n"
                "────────────────────\n"
                "Live location stream is now active."
            )
            await meta_api.send_text_message(rep_phone, rep_alert)

        # Present the 3 transit buttons
        await send_driver_transit_menu(session, clean_p, trip.trip_id)
        return True

    # 2. Driver clicks [Delivery Charges]
    if text_lower.startswith("flt_drv_deliv_"):
        trip_id = text_strip.replace("flt_drv_deliv_", "").strip()
        await set_user_state(
            session,
            clean_p,
            current_step="awaiting_customer_id",
            current_data={"trip_id": trip_id},
            flow_name="fleet_driver"
        )
        prompt = (
            f"📦 *RECORD DELIVERY CHARGE: {trip_id}*\n"
            "────────────────────\n"
            "Please type the Customer ID:\n"
            "_(e.g. CUST-101 or 101)_"
        )
        await meta_api.send_text_message(clean_p, prompt)
        return True

    # 3. Driver clicks [Emergency Charges]
    if text_lower.startswith("flt_drv_emerg_"):
        trip_id = text_strip.replace("flt_drv_emerg_", "").strip()
        header = "EMERGENCY CHARGES"
        body = (
            f"⚠️ *EMERGENCY CHARGES: {trip_id}*\n"
            "────────────────────\n"
            "Please select the emergency charge type:"
        )
        buttons = [
            {"id": f"flt_emg_fuel_{trip_id}", "title": "Emergency Fuel"},
            {"id": f"flt_emg_other_{trip_id}", "title": "Other"}
        ]
        await meta_api.send_button_message(
            to_phone=clean_p,
            body_text=body,
            buttons=buttons,
            header_text=header
        )
        return True

    # 4. Emergency Fuel clicked
    if text_lower.startswith("flt_emg_fuel_"):
        trip_id = text_strip.replace("flt_emg_fuel_", "").strip()
        await set_user_state(
            session,
            clean_p,
            current_step="awaiting_fuel_amount",
            current_data={"trip_id": trip_id},
            flow_name="fleet_driver"
        )
        prompt = (
            f"⛽ *EMERGENCY FUEL: {trip_id}*\n"
            "────────────────────\n"
            "📹 *Requirement:* Please take a 10-second video of the fuel pump reading and vehicle fuel gauge.\n\n"
            "Enter the total amount spent on fuel in USD:\n"
            "_(e.g. 25.00)_"
        )
        await meta_api.send_text_message(clean_p, prompt)
        return True

    # 5. Emergency Other clicked
    if text_lower.startswith("flt_emg_other_"):
        trip_id = text_strip.replace("flt_emg_other_", "").strip()
        await set_user_state(
            session,
            clean_p,
            current_step="awaiting_other_desc",
            current_data={"trip_id": trip_id},
            flow_name="fleet_driver"
        )
        prompt = (
            f"🔧 *EMERGENCY EXPENSE (OTHER): {trip_id}*\n"
            "────────────────────\n"
            "Please describe the emergency issue:\n"
            "_(e.g. Tyre puncture repair at toll gate)_"
        )
        await meta_api.send_text_message(clean_p, prompt)
        return True

    # 6. Payment method clicked: [Cash], [Bank/EcoCash], [Unpaid]
    if text_lower.startswith(("flt_pay_cash_", "flt_pay_bank_", "flt_pay_unpaid_")):
        if text_lower.startswith("flt_pay_cash_"):
            pay_type = "CASH"
            trip_id = text_strip[len("flt_pay_cash_"):].strip()
        elif text_lower.startswith("flt_pay_bank_"):
            pay_type = "BANK_ECOCASH"
            trip_id = text_strip[len("flt_pay_bank_"):].strip()
        else:
            pay_type = "UNPAID"
            trip_id = text_strip[len("flt_pay_unpaid_"):].strip()

        data = (state.current_data or {}) if state else {}
        if not trip_id:
            trip_id = data.get("trip_id", "")
        customer_id = data.get("customer_id", "GENERAL")
        col_amt = float(data.get("collected_amount", 0.0))

        if pay_type == "UNPAID":
            col_amt = 0.0

        await record_driver_delivery_payment(
            session=session,
            trip_id=trip_id,
            customer_id=customer_id,
            collected_amount=col_amt,
            payment_method=pay_type
        )

        ack = (
            f"✅ *PAYMENT RECORDED: {trip_id}*\n"
            "────────────────────\n"
            f"Customer: {customer_id}\n"
            f"Method: {pay_type}\n"
            f"Amount: ${col_amt:,.2f}\n"
            "────────────────────\n"
            "Schedule updated successfully!"
        )
        await meta_api.send_text_message(clean_p, ack)
        await send_driver_transit_menu(session, clean_p, trip_id)
        return True

    # 7. Driver clicks [I am Returning]
    if text_lower.startswith("flt_drv_ret_"):
        trip_id = text_strip.replace("flt_drv_ret_", "").strip()
        trip = await get_fleet_trip_request_by_id(session, trip_id)
        if trip:
            trip.is_live_location_active = False
            trip.returning_at = datetime.datetime.utcnow()
            trip.status = "RETURNING"
            await session.commit()

            # Alert perspective Sales Rep
            if trip.salesperson_phone:
                rep_phone = clean_phone(trip.salesperson_phone)
                rep_alert = (
                    f"↩️ *DRIVER RETURNING: {trip.trip_id}*\n"
                    "────────────────────\n"
                    f"Driver {trip.driver_name} is returning to base depot.\n"
                    "Live location tracking deactivated."
                )
                await meta_api.send_text_message(rep_phone, rep_alert)

        await send_driver_returning_menu(session, clean_p, trip_id)
        return True

    # 8. Driver clicks [I Have Returned]
    if text_lower.startswith("flt_drv_returned_"):
        trip_id = text_strip.replace("flt_drv_returned_", "").strip()
        trip = await get_fleet_trip_request_by_id(session, trip_id)
        if trip:
            trip.status = "RETURNED"
            trip.returned_at = datetime.datetime.utcnow()
            await session.commit()

        await clear_user_state(session, clean_p)
        ack = (
            f"🏢 *RETURN LOGGED: {trip_id}*\n"
            "────────────────────\n"
            "Welcome back! Your return has been recorded.\n"
            "Please proceed to the Sales Admin for physical balancing session."
        )
        await meta_api.send_text_message(clean_p, ack)

        # Summon the Company's assigned Sales Admin for Stage 6
        from app.handlers.sales_admin_handler import notify_sales_admin_balancing_session
        await notify_sales_admin_balancing_session(session, trip_id)
        return True

    # 9. Active state handling for Driver
    if state and state.flow_name == "fleet_driver":
        data = state.current_data or {}
        trip_id = data.get("trip_id", "")

        if text_lower in {"cancel", "exit", "back", "menu", "reset"}:
            if state.current_step == "awaiting_departure_time":
                await clear_user_state(session, clean_p)
                await meta_api.send_text_message(clean_p, "Departure entry cancelled. You can reply when ready.")
                return True
            else:
                await send_driver_transit_menu(session, clean_p, trip_id)
                return True


        # Awaiting departure time
        if state.current_step == "awaiting_departure_time":
            dep_time = text_strip.upper()
            trip = await get_fleet_trip_request_by_id(session, trip_id)
            if trip:
                trip.departure_time = dep_time
                await session.commit()

            ack = (
                f"🕒 *DEPARTURE TIME LOGGED: {trip_id}*\n"
                "────────────────────\n"
                f"Scheduled Departure: *{dep_time}*\n\n"
                "When you start the vehicle and leave the gate, tap the button below:"
            )
            buttons = [
                {"id": f"flt_drv_start_{trip_id}", "title": "Trip Started"}
            ]
            await meta_api.send_button_message(
                to_phone=clean_p,
                body_text=ack,
                buttons=buttons,
                header_text="TRIP READY"
            )
            return True

        # Awaiting Customer ID
        if state.current_step == "awaiting_customer_id":
            cust_id = text_strip.upper()
            data["customer_id"] = cust_id

            # Autonomous lookup in customer schedules
            stmt = select(FleetCustomerSchedule).where(
                FleetCustomerSchedule.trip_id == trip_id,
                FleetCustomerSchedule.customer_id == cust_id
            )
            res = await session.execute(stmt)
            sched = res.scalars().first()

            exp_str = f"${sched.expected_charge:,.2f}" if sched else "Not registered"
            data["expected_charge"] = sched.expected_charge if sched else 0.0

            await set_user_state(session, clean_p, "awaiting_collected_amount", data, flow_name="fleet_driver")
            prompt = (
                f"📦 *CUSTOMER: {cust_id}*\n"
                f"Expected Transport Charge: *{exp_str}*\n"
                "────────────────────\n"
                "Enter amount collected in USD:\n"
                "_(e.g. 45.00 or 0 if unpaid)_"
            )
            await meta_api.send_text_message(clean_p, prompt)
            return True

        # Awaiting Collected Amount -> Ask Payment Method
        if state.current_step == "awaiting_collected_amount":
            clean_val = re.sub(r"[^\d.]", "", text_strip)
            try:
                col_amt = float(clean_val)
                if col_amt < 0:
                    raise ValueError()
            except ValueError:
                await meta_api.send_text_message(clean_p, "⚠️ Please enter a valid number (e.g. 45.00 or 0):")
                return True

            data["collected_amount"] = col_amt
            cust_id = data.get("customer_id", "")
            await set_user_state(session, clean_p, "awaiting_payment_method", data, flow_name="fleet_driver")

            header = "PAYMENT METHOD"
            body = (
                f"💵 *SELECT PAYMENT METHOD*\n"
                f"Customer: {cust_id} | Amount: ${col_amt:,.2f}\n"
                "────────────────────\n"
                "How was this delivery charge paid?"
            )
            buttons = [
                {"id": f"flt_pay_cash_{trip_id}", "title": "Cash"},
                {"id": f"flt_pay_bank_{trip_id}", "title": "Bank/EcoCash"},
                {"id": f"flt_pay_unpaid_{trip_id}", "title": "Unpaid"}
            ]
            await meta_api.send_button_message(
                to_phone=clean_p,
                body_text=body,
                buttons=buttons,
                header_text=header
            )
            return True

        # Awaiting Emergency Fuel Amount
        if state.current_step == "awaiting_fuel_amount":
            if "video" in text_strip.lower():
                await meta_api.send_text_message(
                    clean_p,
                    "📹 *Fuel pump video received!*\n\nNow please type the total amount spent on fuel in USD:\n_(e.g. 25.00)_"
                )
                return True

            clean_val = re.sub(r"[^\d.]", "", text_strip)
            try:
                fuel_amt = float(clean_val)
                if fuel_amt <= 0:
                    raise ValueError()
            except ValueError:
                await meta_api.send_text_message(clean_p, "⚠️ Please enter a valid positive number for fuel cost (e.g. 25.00):")
                return True

            await record_emergency_expense(
                session=session,
                trip_id=trip_id,
                driver_phone=clean_p,
                charge_type="EMERGENCY_FUEL",
                amount=fuel_amt,
                description="Emergency Diesel/Petrol refuel",
                has_video=True
            )
            await meta_api.send_text_message(
                clean_p,
                f"⛽ *EMERGENCY FUEL LOGGED*\n────────────────────\nAmount: ${fuel_amt:,.2f}\nLogged for balancing."
            )
            await send_driver_transit_menu(session, clean_p, trip_id)
            return True

        # Awaiting Other Emergency Description
        if state.current_step == "awaiting_other_desc":
            desc = text_strip
            data["other_desc"] = desc
            await set_user_state(session, clean_p, "awaiting_other_amount", data, flow_name="fleet_driver")
            prompt = (
                f"🔧 *EMERGENCY EXPENSE: {trip_id}*\n"
                f"Issue: {desc}\n"
                "────────────────────\n"
                "How much money was spent on this issue in USD?\n"
                "_(e.g. 15.00)_"
            )
            await meta_api.send_text_message(clean_p, prompt)
            return True

        # Awaiting Other Emergency Amount
        if state.current_step == "awaiting_other_amount":
            clean_val = re.sub(r"[^\d.]", "", text_strip)
            try:
                other_amt = float(clean_val)
                if other_amt <= 0:
                    raise ValueError()
            except ValueError:
                await meta_api.send_text_message(clean_p, "⚠️ Please enter a valid amount (e.g. 15.00):")
                return True

            desc = data.get("other_desc", "Emergency expense")
            await record_emergency_expense(
                session=session,
                trip_id=trip_id,
                driver_phone=clean_p,
                charge_type="OTHER",
                amount=other_amt,
                description=desc
            )
            await meta_api.send_text_message(
                clean_p,
                f"🔧 *EMERGENCY EXPENSE LOGGED*\n────────────────────\nIssue: {desc}\nAmount: ${other_amt:,.2f}\nLogged for balancing."
            )
            await send_driver_transit_menu(session, clean_p, trip_id)
            return True

    return False
