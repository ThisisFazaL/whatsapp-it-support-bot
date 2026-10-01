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
    FleetEmergencyExpense,
    get_fleet_trip_request_by_id,
    get_active_trip_for_driver,
    record_driver_delivery_payment,
    record_emergency_expense,
    get_emergency_expense_by_id,
    set_emergency_expense_status
)
from app.state_manager import set_user_state, clear_user_state, get_user_state, normalize_phone_number
from app.meta_api import meta_api
from app.services.ai_extractor import extract_odometer_from_image

logger = logging.getLogger("driver_handler")


def clean_phone(phone: Optional[str]) -> str:
    return normalize_phone_number(str(phone or ""))



async def send_driver_transit_menu(session: AsyncSession, phone: str, trip_id: str):
    """Presents the live transit buttons to Driver (Emergency Charges & I Have Returned)."""
    header = "TRIP IN TRANSIT"
    body = (
        f"🚛 *TRIP IN TRANSIT: {trip_id}*\n"
        "────────────────────\n"
        "Trip is in progress.\n"
        "Please select an option below:"
    )

    buttons = [
        {"id": f"flt_drv_emerg_{trip_id}", "title": "Emergency Charges"},
        {"id": f"flt_drv_returned_{trip_id}", "title": "I Have Returned"}
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
    """Presents returning menu to Driver when vehicle is heading back to depot."""
    header = "RETURNING TO BASE"
    body = (
        f"↩️ *RETURNING TO BASE: {trip_id}*\n"
        "────────────────────\n"
        "Vehicle is returning to depot.\n"
        "Tap below upon arrival at base depot:"
    )
    buttons = [
        {"id": f"flt_drv_emerg_{trip_id}", "title": "Emergency Charges"},
        {"id": f"flt_drv_returned_{trip_id}", "title": "I Have Returned"}
    ]
    await set_user_state(
        session,
        phone,
        current_step="in_transit",
        current_data={"trip_id": trip_id, "returning": True},
        flow_name="fleet_driver"
    )
    await meta_api.send_button_message(
        to_phone=phone,
        body_text=body,
        buttons=buttons,
        header_text=header
    )


async def return_to_appropriate_driver_menu(session: AsyncSession, phone: str, trip_id: str):
    """Returns the driver to either the transit menu or returning menu based on trip status."""
    trip = await get_fleet_trip_request_by_id(session, trip_id)
    if trip and trip.status == "RETURNING":
        await send_driver_returning_menu(session, phone, trip_id)
    else:
        await send_driver_transit_menu(session, phone, trip_id)


async def notify_panashe_return_logged(trip_id: str, message_text: str):
    """
    Sends the RETURN LOGGED notification card to Logistics Assistant Panashe.
    """
    from app.handlers.fleet_approval_handler import get_solo_test_mode
    is_solo = get_solo_test_mode()
    recipients = [clean_phone(settings.master_admin_phone)] if is_solo else [
        clean_phone(p) for p in getattr(settings, "panashe_phones", ["263777261203", "263785322640"]) if p
    ]
    for p in set(recipients):
        try:
            await meta_api.send_text_message(p, message_text)
            logger.info(f"Delivered RETURN LOGGED notification for {trip_id} to Panashe ({p})")
        except Exception as e:
            logger.warning(f"Could not deliver RETURN LOGGED to Panashe ({p}): {e}")


async def handle_driver_interaction(
    session: AsyncSession,
    phone: str,
    message_text: str,
    state: Optional[Any],
    image_id: Optional[str] = None
) -> bool:
    """
    Handles all interactions for Driver (Stage 5).
    Returns True if handled, False otherwise.
    """
    clean_p = clean_phone(phone)
    text_strip = message_text.strip()
    text_lower = text_strip.lower()

    # 0. Emergency Expense Approval by Edward / Zayn / Master Admin
    if text_lower.startswith(("flt_emg_appr_", "flt_emg_rej_")):
        is_approve = text_lower.startswith("flt_emg_appr_")
        exp_id_str = text_strip.replace("flt_emg_appr_", "").replace("flt_emg_rej_", "").strip()
        try:
            exp_id = int(exp_id_str)
        except ValueError:
            exp_id = 0

        exp = await get_emergency_expense_by_id(session, exp_id)
        if not exp:
            await meta_api.send_text_message(clean_p, f"⚠️ Emergency expense #{exp_id} not found.")
            return True

        new_status = "APPROVED" if is_approve else "REJECTED"
        approver_name = "Edward / Zayn"
        if clean_p == clean_phone(settings.edward_phone):
            approver_name = "Edward (Logistics)"
        elif clean_p == clean_phone(settings.zayn_phone):
            approver_name = "Zayn (Accounts)"
        elif clean_p == clean_phone(settings.master_admin_phone):
            approver_name = "Master Admin"

        await set_emergency_expense_status(session, exp_id, new_status, approver_name)

        # Acknowledge Approver
        status_icon = "✅" if is_approve else "❌"
        ack_approver = (
            f"{status_icon} *EMERGENCY EXPENSE {new_status}*\n"
            "────────────────────\n"
            f"Trip: *{exp.trip_id}*\n"
            f"Type: *{exp.charge_type}*\n"
            f"Amount: *${exp.amount:,.2f}*\n"
            f"Decision logged by {approver_name}."
        )
        await meta_api.send_text_message(clean_p, ack_approver)

        # Notify Driver
        drv_phone = clean_phone(exp.driver_phone)
        if is_approve:
            drv_msg = (
                f"✅ *EMERGENCY EXPENSE APPROVED*\n"
                "────────────────────\n"
                f"Trip: *{exp.trip_id}*\n"
                f"Type: *{exp.charge_type}*\n"
                f"Approved Amount: *${exp.amount:,.2f}*\n"
                f"Approved by: *{approver_name}*\n"
                "────────────────────\n"
                "You may proceed with the expenditure. Please retain receipt/evidence for final balancing."
            )
        else:
            drv_msg = (
                f"❌ *EMERGENCY EXPENSE REJECTED*\n"
                "────────────────────\n"
                f"Trip: *{exp.trip_id}*\n"
                f"Amount: *${exp.amount:,.2f}*\n"
                f"Declined by: *{approver_name}*\n"
                "────────────────────\n"
                "Please contact Logistics for assistance."
            )
        await meta_api.send_text_message(drv_phone, drv_msg)
        return True

    # 0.5 Location pin message - Disabled for anti-hijacking & cargo security
    if text_lower.startswith("location_pin_"):
        sec_msg = (
            "🔒 *SECURITY PROTOCOL*\n"
            "────────────────────\n"
            "Live location sharing over WhatsApp is disabled for cargo protection and anti-hijacking safety.\n"
            "Vehicle tracking is managed securely via fleet control."
        )
        await meta_api.send_text_message(clean_p, sec_msg)
        return True

    # 1. Driver clicks [Trip Started] -> Prompt for Start Odometer reading
    if text_lower.startswith("flt_drv_start_"):
        trip_id = text_strip.replace("flt_drv_start_", "").strip()
        trip = await get_fleet_trip_request_by_id(session, trip_id)
        if not trip:
            await meta_api.send_text_message(clean_p, f"⚠️ Trip {trip_id} not found.")
            return True

        await set_user_state(
            session,
            clean_p,
            current_step="awaiting_start_odometer",
            current_data={"trip_id": trip_id},
            flow_name="fleet_driver"
        )
        prompt = (
            f"🚚 *TRIP DEPARTURE: {trip_id}*\n"
            "────────────────────\n"
            "📸 *Please take and send a photo of the vehicle's dashboard / Starting Odometer:*\n\n"
            "_(Our AI will automatically verify your starting mileage from the photo.)_"
        )
        await meta_api.send_text_message(clean_p, prompt)
        return True

    # 2. Driver clicks [Delivery Charges] -> Delivery charges collection by driver is disabled
    if text_lower.startswith("flt_drv_deliv_"):
        trip_id = text_strip.replace("flt_drv_deliv_", "").strip()
        await meta_api.send_text_message(
            clean_p,
            f"ℹ️ *DELIVERY CHARGES REMOVED: {trip_id}*\n"
            "────────────────────\n"
            "Delivery charges collection by driver is disabled.\n"
            "Please report emergency expenses if needed, or tap 'I Have Returned' upon depot arrival."
        )
        await return_to_appropriate_driver_menu(session, clean_p, trip_id)
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
            "📹 *Video Verification Protocol:*\n"
            "• Record a video showing the *fuel pump meter* and *truck fuel gauge*.\n"
            "• Speak the current *date and time* in the background.\n"
            "⚠️ *Do NOT send this video to WhatsApp.* Keep it on your phone to show during physical balancing!\n\n"
            "Now please type the total amount spent on fuel in USD:\n"
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
        await return_to_appropriate_driver_menu(session, clean_p, trip_id)
        return True

    # 7. Driver clicks [I Have Returned] -> Prompt for final Return Odometer reading
    if text_lower.startswith(("flt_drv_returned_", "flt_drv_retd_", "flt_drv_ret_")) or text_lower in {"i have returned", "returned", "have returned", "i am returning"}:
        trip_id = ""
        for pfx in ["flt_drv_returned_", "flt_drv_retd_", "flt_drv_ret_"]:
            if text_strip.startswith(pfx):
                trip_id = text_strip[len(pfx):].strip()
                break

        if not trip_id and state and state.current_data:
            trip_id = state.current_data.get("trip_id", "")

        trip = await get_fleet_trip_request_by_id(session, trip_id) if trip_id else None
        if not trip:
            trip = await get_active_trip_for_driver(session, clean_p)

        if not trip:
            await meta_api.send_text_message(clean_p, "⚠️ Active trip not found.")
            return True

        trip_id = trip.trip_id
        if not trip.returning_at:
            trip.returning_at = datetime.datetime.utcnow()
        trip.status = "RETURNING"
        trip.is_live_location_active = False
        await session.commit()

        # Alert perspective Sales Rep
        if trip.salesperson_phone:
            rep_phone = clean_phone(trip.salesperson_phone)
            rep_alert = (
                f"↩️ *DRIVER RETURNED: {trip.trip_id}*\n"
                "────────────────────\n"
                f"Driver {trip.driver_name} has arrived back at base depot."
            )
            await meta_api.send_text_message(rep_phone, rep_alert)

        await set_user_state(
            session,
            clean_p,
            current_step="awaiting_return_odometer",
            current_data={"trip_id": trip_id},
            flow_name="fleet_driver"
        )
        prompt = (
            f"🏁 *DEPOT ARRIVAL: {trip_id}*\n"
            "────────────────────\n"
            "📸 *Please take and send a photo of the vehicle's dashboard / Return Odometer:*\n\n"
            "_(Our AI will automatically verify your final return mileage from the photo.)_"
        )
        await meta_api.send_text_message(clean_p, prompt)
        return True

    # 8.5 Odometer Confirmation from Image Detection
    if text_lower.startswith("flt_odo_ok_start_"):
        raw_payload = text_strip[len("flt_odo_ok_start_"):].strip()
        parts = raw_payload.split("_")
        trip_id = parts[0]
        odo_val_str = parts[1] if len(parts) > 1 else ""
        try:
            odo_val = float(odo_val_str)
        except ValueError:
            odo_val = 0.0

        trip = await get_fleet_trip_request_by_id(session, trip_id)
        if trip and odo_val > 0:
            trip.start_odometer = odo_val
            trip.status = "ACTIVE"
            trip.departed_at = datetime.datetime.utcnow()
            await session.commit()

            if trip.salesperson_phone:
                rep_phone = clean_phone(trip.salesperson_phone)
                rep_alert = (
                    f"🚛 *TRIP STARTED: {trip.trip_id}*\n"
                    "────────────────────\n"
                    f"Driver: *{trip.driver_name}*\n"
                    f"Truck: *{trip.truck_plate}*\n"
                    f"Start Odometer: *{odo_val:,.0f} KM* (Verified 📸)\n"
                    f"Departure Time: *{trip.departure_time or 'Just now'}*\n"
                    "────────────────────\n"
                    "Trip is now in transit."
                )
                await meta_api.send_text_message(rep_phone, rep_alert)

        ack = (
            f"✅ *TRIP STARTED: {trip_id}*\n"
            "────────────────────\n"
            f"Start Odometer: *{odo_val:,.0f} KM*\n"
            "Drive safely! Please report emergency expenses as needed, and tap 'I Have Returned' upon depot arrival."
        )
        await meta_api.send_text_message(clean_p, ack)
        await send_driver_transit_menu(session, clean_p, trip_id)
        return True

    if text_lower.startswith("flt_odo_ok_end_"):
        raw_payload = text_strip[len("flt_odo_ok_end_"):].strip()
        parts = raw_payload.split("_")
        trip_id = parts[0]
        odo_val_str = parts[1] if len(parts) > 1 else ""
        try:
            end_odo = float(odo_val_str)
        except ValueError:
            end_odo = 0.0

        trip = await get_fleet_trip_request_by_id(session, trip_id)
        dist_km = 0.0
        if trip and end_odo > 0:
            start_odo = trip.start_odometer or 0.0
            dist_km = max(0.0, end_odo - start_odo) if start_odo > 0 else 0.0
            trip.end_odometer = end_odo
            trip.distance_km = dist_km
            trip.status = "RETURNED"
            trip.returned_at = datetime.datetime.utcnow()
            await session.commit()

        await clear_user_state(session, clean_p)
        start_disp = trip.start_odometer or 0 if trip else 0
        ack = (
            f"🏢 *RETURN LOGGED: {trip_id}*\n"
            "────────────────────\n"
            f"Start Odometer: *{start_disp:,.0f} KM*\n"
            f"Return Odometer: *{end_odo:,.0f} KM* (Verified 📸)\n"
            f"Total Distance Covered: *{dist_km:,.0f} KM*\n"
            "────────────────────\n"
            "Welcome back! Please proceed to the Sales Admin for physical balancing session."
        )
        await meta_api.send_text_message(clean_p, ack)
        await notify_panashe_return_logged(trip_id, ack)

        from app.handlers.sales_admin_handler import notify_sales_admin_balancing_session
        await notify_sales_admin_balancing_session(session, trip_id)
        return True

    if text_lower.startswith(("flt_odo_edit_start_", "flt_odo_edit_end_")):
        is_start = text_lower.startswith("flt_odo_edit_start_")
        trip_id = text_strip.replace("flt_odo_edit_start_", "").replace("flt_odo_edit_end_", "").strip()
        target_step = "awaiting_start_odometer" if is_start else "awaiting_return_odometer"
        await set_user_state(
            session,
            clean_p,
            current_step=target_step,
            current_data={"trip_id": trip_id},
            flow_name="fleet_driver"
        )
        prompt = (
            f"✏️ *MANUAL ODOMETER ENTRY: {trip_id}*\n"
            "────────────────────\n"
            f"Please enter the vehicle's *{'Starting' if is_start else 'Return'} Odometer* reading (in KM):\n"
            "_(e.g. 145200)_"
        )
        await meta_api.send_text_message(clean_p, prompt)
        return True

    # 9. Active state handling for Driver
    if state and state.flow_name == "fleet_driver":
        data = state.current_data or {}
        trip_id = data.get("trip_id", "")

        if text_lower in {"cancel", "exit", "back", "menu", "reset"}:
            if state.current_step in {"awaiting_departure_time", "awaiting_start_odometer"}:
                await clear_user_state(session, clean_p)
                await meta_api.send_text_message(clean_p, "Action cancelled. You can reply when ready.")
                return True
            else:
                await return_to_appropriate_driver_menu(session, clean_p, trip_id)
                return True

        # Awaiting Start Odometer reading
        if state.current_step == "awaiting_start_odometer":
            if image_id:
                img_bytes = await meta_api.download_media_bytes(image_id)
                detected_odo = await extract_odometer_from_image(img_bytes) if img_bytes else None
                if detected_odo and detected_odo > 0:
                    odo_int_str = f"{int(detected_odo)}"
                    prompt = (
                        f"📸 *ODOMETER DETECTED: {detected_odo:,.0f} KM*\n"
                        "────────────────────\n"
                        f"We detected *{detected_odo:,.0f} KM* from your dashboard photo.\n\n"
                        "Tap below to confirm, or reply with the correct numbers if different:"
                    )
                    buttons = [
                        {"id": f"flt_odo_ok_start_{trip_id}_{odo_int_str}", "title": "✅ Confirm Reading"},
                        {"id": f"flt_odo_edit_start_{trip_id}", "title": "✏️ Enter Manually"}
                    ]
                    await meta_api.send_button_message(
                        to_phone=clean_p,
                        body_text=prompt,
                        buttons=buttons,
                        header_text="ODOMETER VERIFICATION"
                    )
                    return True
                else:
                    await meta_api.send_text_message(
                        clean_p,
                        "⚠️ *Could not read odometer from photo*\n\n"
                        "We couldn't clearly detect the odometer reading. "
                        "Please reply with the numbers manually (e.g. *145200*) or send a clearer photo."
                    )
                    return True

            clean_val = re.sub(r"[^\d.]", "", text_strip)
            try:
                odo_val = float(clean_val)
                if odo_val <= 0:
                    raise ValueError()
            except ValueError:
                await meta_api.send_text_message(
                    clean_p,
                    "📸 Please send a photo of the vehicle's dashboard cluster, or reply with the odometer numbers manually (e.g. *145200*):"
                )
                return True

            trip = await get_fleet_trip_request_by_id(session, trip_id)
            if trip:
                trip.start_odometer = odo_val
                trip.status = "ACTIVE"
                trip.departed_at = datetime.datetime.utcnow()
                await session.commit()

                # Alert perspective Sales Rep
                if trip.salesperson_phone:
                    rep_phone = clean_phone(trip.salesperson_phone)
                    rep_alert = (
                        f"🚛 *TRIP STARTED: {trip.trip_id}*\n"
                        "────────────────────\n"
                        f"Driver: *{trip.driver_name}*\n"
                        f"Truck: *{trip.truck_plate}*\n"
                        f"Start Odometer: *{odo_val:,.0f} KM*\n"
                        f"Departure Time: *{trip.departure_time or 'Just now'}*\n"
                        "────────────────────\n"
                        "Trip is now in transit."
                    )
                    await meta_api.send_text_message(rep_phone, rep_alert)

            ack = (
                f"✅ *TRIP STARTED: {trip_id}*\n"
                "────────────────────\n"
                f"Start Odometer: *{odo_val:,.0f} KM*\n"
                "Drive safely! Please report emergency expenses as needed, and tap 'I Have Returned' upon depot arrival."
            )
            await meta_api.send_text_message(clean_p, ack)
            await send_driver_transit_menu(session, clean_p, trip_id)
            return True

        # Awaiting Return Odometer reading
        if state.current_step == "awaiting_return_odometer":
            if image_id:
                img_bytes = await meta_api.download_media_bytes(image_id)
                detected_odo = await extract_odometer_from_image(img_bytes) if img_bytes else None
                if detected_odo and detected_odo > 0:
                    odo_int_str = f"{int(detected_odo)}"
                    prompt = (
                        f"📸 *ODOMETER DETECTED: {detected_odo:,.0f} KM*\n"
                        "────────────────────\n"
                        f"We detected *{detected_odo:,.0f} KM* from your dashboard photo.\n\n"
                        "Tap below to confirm, or reply with the correct numbers if different:"
                    )
                    buttons = [
                        {"id": f"flt_odo_ok_end_{trip_id}_{odo_int_str}", "title": "✅ Confirm Reading"},
                        {"id": f"flt_odo_edit_end_{trip_id}", "title": "✏️ Enter Manually"}
                    ]
                    await meta_api.send_button_message(
                        to_phone=clean_p,
                        body_text=prompt,
                        buttons=buttons,
                        header_text="ODOMETER VERIFICATION"
                    )
                    return True
                else:
                    await meta_api.send_text_message(
                        clean_p,
                        "⚠️ *Could not read odometer from photo*\n\n"
                        "We couldn't clearly detect the odometer reading. "
                        "Please reply with the numbers manually (e.g. *145580*) or send a clearer photo."
                    )
                    return True

            clean_val = re.sub(r"[^\d.]", "", text_strip)
            try:
                end_odo = float(clean_val)
                if end_odo <= 0:
                    raise ValueError()
            except ValueError:
                await meta_api.send_text_message(
                    clean_p,
                    "📸 Please send a photo of the vehicle's dashboard cluster, or reply with the odometer numbers manually (e.g. *145580*):"
                )
                return True

            trip = await get_fleet_trip_request_by_id(session, trip_id)
            dist_km = 0.0
            if trip:
                start_odo = trip.start_odometer or 0.0
                dist_km = max(0.0, end_odo - start_odo) if start_odo > 0 else 0.0
                trip.end_odometer = end_odo
                trip.distance_km = dist_km
                trip.status = "RETURNED"
                trip.returned_at = datetime.datetime.utcnow()
                await session.commit()

            await clear_user_state(session, clean_p)
            ack = (
                f"🏢 *RETURN LOGGED: {trip_id}*\n"
                "────────────────────\n"
                f"Start Odometer: *{trip.start_odometer or 0:,.0f} KM*\n"
                f"Return Odometer: *{end_odo:,.0f} KM*\n"
                f"Total Distance Covered: *{dist_km:,.0f} KM*\n"
                "────────────────────\n"
                "Welcome back! Please proceed to the Sales Admin for physical balancing session."
            )
            await meta_api.send_text_message(clean_p, ack)
            await notify_panashe_return_logged(trip_id, ack)

            # Summon the Company's assigned Sales Admin for Stage 6
            from app.handlers.sales_admin_handler import notify_sales_admin_balancing_session
            await notify_sales_admin_balancing_session(session, trip_id)
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

        # Awaiting Customer Number Selection (Driver replies 1, 2, 3...)
        if state.current_step == "awaiting_customer_number":
            customers_map = data.get("customers_map", {})
            choice = text_strip.strip()
            selected_cust_id = customers_map.get(choice)
            if not selected_cust_id:
                # Also allow direct customer code/name lookup
                for k, v in customers_map.items():
                    if choice.upper() == v.upper() or choice.upper() in v.upper():
                        selected_cust_id = v
                        break

            if not selected_cust_id:
                await meta_api.send_text_message(
                    clean_p,
                    f"⚠️ Please reply with a valid customer number (1 to {len(customers_map)}) or type the Customer ID:"
                )
                return True

            data["customer_id"] = selected_cust_id
            # Lookup customer record
            stmt = select(FleetCustomerSchedule).where(
                FleetCustomerSchedule.trip_id == trip_id,
                FleetCustomerSchedule.customer_id == selected_cust_id
            )
            res = await session.execute(stmt)
            sched = res.scalars().first()
            data["expected_charge"] = sched.expected_charge if sched else 0.0

            disp_name = sched.reference_note or selected_cust_id if sched else selected_cust_id
            await set_user_state(session, clean_p, "awaiting_collected_amount", data, flow_name="fleet_driver")
            prompt = (
                f"📦 *CUSTOMER: {disp_name}*\n"
                "────────────────────\n"
                "Please enter the amount collected in USD:\n"
                "_(e.g. 45.00 or 0 if unpaid)_"
            )
            await meta_api.send_text_message(clean_p, prompt)
            return True

        # Awaiting Customer ID (Blind Entry: NEVER reveal expected charge to driver)
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
            data["expected_charge"] = sched.expected_charge if sched else 0.0

            await set_user_state(session, clean_p, "awaiting_collected_amount", data, flow_name="fleet_driver")
            prompt = (
                f"📦 *CUSTOMER: {cust_id}*\n"
                "────────────────────\n"
                "Please enter the amount collected in USD:\n"
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

        # Awaiting Emergency Fuel Amount -> Route for Approval by Edward or Zayn
        if state.current_step == "awaiting_fuel_amount":
            if image_id or "video" in text_strip.lower():
                await meta_api.send_text_message(
                    clean_p,
                    "⚠️ *Please do NOT send the video here.*\n"
                    "Keep the video saved on your phone to present to the Sales Admin during physical balancing.\n\n"
                    "Please reply with the *USD fuel amount* only (e.g. 25.00):"
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

            exp = await record_emergency_expense(
                session=session,
                trip_id=trip_id,
                driver_phone=clean_p,
                charge_type="EMERGENCY_FUEL",
                amount=fuel_amt,
                description="Emergency Diesel/Petrol refuel",
                has_video=True,
                status="PENDING"
            )

            # Send authorization request to Edward & Zayn (or Master Admin in solo mode)
            from app.handlers.fleet_approval_handler import get_solo_test_mode
            is_solo = get_solo_test_mode()
            approvers = [clean_phone(settings.master_admin_phone)] if is_solo else [
                clean_phone(settings.edward_phone),
                clean_phone(settings.zayn_phone)
            ]

            emg_alert = (
                f"⛽ *EMERGENCY FUEL REQUEST*\n"
                "────────────────────\n"
                f"Trip: *{trip_id}*\n"
                f"Driver: `{clean_p}`\n"
                f"Expense: *Diesel/Petrol*\n"
                f"Requested: *${fuel_amt:,.2f}*\n"
                "────────────────────\n"
                "Please approve or decline this driver expense:"
            )
            buttons = [
                {"id": f"flt_emg_appr_{exp.id}", "title": "Approve Expense"},
                {"id": f"flt_emg_rej_{exp.id}", "title": "Reject Expense"}
            ]
            for ap_phone in set(approvers):
                await meta_api.send_button_message(
                    to_phone=ap_phone,
                    body_text=emg_alert,
                    buttons=buttons,
                    header_text="EMERGENCY REQUEST"
                )

            await meta_api.send_text_message(
                clean_p,
                f"⏳ *EMERGENCY FUEL SUBMITTED*\n────────────────────\nAmount: *${fuel_amt:,.2f}*\nApproval request dispatched to Edward & Zayn.\nYou will be notified immediately when approved."
            )
            await return_to_appropriate_driver_menu(session, clean_p, trip_id)
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

        # Awaiting Other Emergency Amount -> Route for Approval by Edward or Zayn
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
            exp = await record_emergency_expense(
                session=session,
                trip_id=trip_id,
                driver_phone=clean_p,
                charge_type="OTHER",
                amount=other_amt,
                description=desc,
                status="PENDING"
            )

            # Send authorization request to Edward & Zayn (or Master Admin in solo mode)
            from app.handlers.fleet_approval_handler import get_solo_test_mode
            is_solo = get_solo_test_mode()
            approvers = [clean_phone(settings.master_admin_phone)] if is_solo else [
                clean_phone(settings.edward_phone),
                clean_phone(settings.zayn_phone)
            ]

            emg_alert = (
                f"🔧 *EMERGENCY EXPENSE REQUEST*\n"
                "────────────────────\n"
                f"Trip: *{trip_id}*\n"
                f"Driver: `{clean_p}`\n"
                f"Issue: *{desc}*\n"
                f"Requested: *${other_amt:,.2f}*\n"
                "────────────────────\n"
                "Please approve or decline this driver expense:"
            )
            buttons = [
                {"id": f"flt_emg_appr_{exp.id}", "title": "Approve Expense"},
                {"id": f"flt_emg_rej_{exp.id}", "title": "Reject Expense"}
            ]
            for ap_phone in set(approvers):
                await meta_api.send_button_message(
                    to_phone=ap_phone,
                    body_text=emg_alert,
                    buttons=buttons,
                    header_text="EMERGENCY REQUEST"
                )

            await meta_api.send_text_message(
                clean_p,
                f"⏳ *EMERGENCY EXPENSE SUBMITTED*\n────────────────────\nIssue: {desc}\nAmount: *${other_amt:,.2f}*\nApproval request dispatched to Edward & Zayn.\nYou will be notified immediately when approved."
            )
            await return_to_appropriate_driver_menu(session, clean_p, trip_id)
            return True

    return False
