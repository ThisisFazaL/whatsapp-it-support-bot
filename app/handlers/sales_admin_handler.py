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



def get_sales_admin_phones_for_company(company_name: str) -> List[str]:
    c_lower = (company_name or "").lower()
    if "lg" in c_lower:
        phones = [clean_phone(settings.sales_admin_lg_phone)]
        if getattr(settings, "sales_admin_lg_backup_phone", None):
            phones.append(clean_phone(settings.sales_admin_lg_backup_phone))
        return [p for p in phones if p]
    elif "kreckle" in c_lower:
        return [clean_phone(settings.sales_admin_kreckle_phone)]
    else:
        return [clean_phone(settings.sales_admin_tg_phone)]


def get_sales_admin_phone_for_company(company_name: str) -> str:
    phones = get_sales_admin_phones_for_company(company_name)
    return phones[0] if phones else clean_phone(settings.sales_admin_tg_phone)


async def notify_sales_admin_balancing_session(session: AsyncSession, trip_id: str):
    """
    Summons the assigned company Sales Admin for physical balancing session.
    Presents complete customer reconciliation card.
    """
    summary = await get_trip_reconciliation_summary(session, trip_id)
    trip: Optional[FleetTripRequest] = summary.get("trip")
    if not trip:
        return

    admin_phones = get_sales_admin_phones_for_company(trip.company_name)
    admin_phone = admin_phones[0] if admin_phones else clean_phone(settings.sales_admin_tg_phone)
    schedules = summary.get("schedules", [])
    emergencies = summary.get("emergencies", [])

    sched_lines = []
    for s in schedules:
        disp_name = s.reference_note or s.customer_id
        if s.reference_note and s.reference_note != s.customer_id:
            disp_name = f"{s.reference_note} ({s.customer_id})"
        sched_lines.append(
            f"• {disp_name}: Exp ${s.expected_charge:,.2f} | Col ${s.collected_charge:,.2f} ({s.payment_method}) [{s.status}]"
        )
    sched_text = "\n".join(sched_lines) if sched_lines else "• No customer schedule records."

    emg_lines = []
    has_fuel_emg = False
    for e in emergencies:
        if e.charge_type == "EMERGENCY_FUEL":
            has_fuel_emg = True
        emg_lines.append(f"• {e.charge_type}: ${e.amount:,.2f} ({e.description or ''})")
    emg_text = "\n".join(emg_lines) if emg_lines else "• None"
    if has_fuel_emg:
        emg_text += "\n💡 _Driver to present physical receipt from trip._"

    from app.handlers.fleet_approval_handler import get_solo_test_mode
    is_solo = get_solo_test_mode()
    header = "BALANCING SESSION"
    tag = "🎭 *[SOLO TEST: SIMULATING SALES ADMIN]*\n" if is_solo else ""
    body = (
        f"{tag}TRANSPORTATION CHARGES BALANCING SESSION\n"
        "────────────────────\n"
        f"Company: {trip.company_name}\n"
        f"Trip: {trip.trip_id} | Route: {trip.route or trip.destination_city}\n"
        f"Driver: {trip.driver_name} | Truck: {trip.truck_plate}\n"
        "────────────────────\n"
        f"Customer Transport Collections:\n{sched_text}\n"
        "────────────────────\n"
        f"Emergency Expenses:\n{emg_text}\n"
        "────────────────────\n"
        f"Allowance Paid: ${summary.get('total_allowance', 0.0):,.2f}\n"
        f"Expected Transport Charges: ${summary.get('total_collected', 0.0):,.2f}\n"
        f"💵 Physical Cash Due: ${summary.get('cash_collected', 0.0):,.2f}\n"
        f"💳 Bank/EcoCash: ${summary.get('bank_collected', 0.0):,.2f}\n"
        "────────────────────\n"
        "Verify transportation charges and select status:"
    )
    buttons = [
        {"id": f"flt_adm_bal_{trip.trip_id}", "title": "Balanced"},
        {"id": f"flt_adm_unbal_{trip.trip_id}", "title": "Not Balanced"}
    ]

    tester_phones = {clean_phone(settings.master_admin_phone)}
    if trip.salesperson_phone:
        tester_phones.add(clean_phone(trip.salesperson_phone))

    recipients = tester_phones if is_solo else set(admin_phones)
    if not is_solo and getattr(settings, "test_user_role", "").upper() == "SALES_ADMIN":
        recipients.update(tester_phones)

    for r in recipients:
        if r:
            await meta_api.send_button_message(
                to_phone=r,
                body_text=body,
                buttons=buttons,
                header_text=header
            )
    logger.info(f"Delivered Stage 6 balancing card for {trip_id} to Sales Admin ({admin_phones})")


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

    # 1. Sales Admin clicks [Balanced] -> Provide option for Sales Admin to close the trip directly
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
            "Transportation charges confirmed balanced in full.\n\n"
            "Tap below to close this trip:"
        )
        buttons = [
            {"id": f"flt_adm_close_{trip.trip_id}", "title": "Close Trip"}
        ]
        await meta_api.send_button_message(
            to_phone=clean_p,
            body_text=ack,
            buttons=buttons,
            header_text="CLOSE TRIP"
        )
        return True

    # 1.5 Sales Admin clicks [Close Trip]
    if text_lower.startswith("flt_adm_close_"):
        trip_id = text_strip.replace("flt_adm_close_", "").strip()
        trip = await get_fleet_trip_request_by_id(session, trip_id)
        if not trip:
            await meta_api.send_text_message(clean_p, f"⚠️ Trip {trip_id} not found.")
            return True

        from app.handlers.logistics_manager_handler import broadcast_confidential_trip_closed
        await broadcast_confidential_trip_closed(session, trip_id)
        await clear_user_state(session, clean_p)

        ack = (
            f"🏁 *TRIP CLOSED: {trip_id}*\n"
            "────────────────────\n"
            "Trip has been officially closed and completed."
        )
        await meta_api.send_text_message(clean_p, ack)
        return True

    # 1.8 Sales Admin clicks [Updated] button
    if text_lower.startswith("flt_adm_fav_updated_"):
        trip_id = text_strip.replace("flt_adm_fav_updated_", "").strip()
        data = (state.current_data if state and state.flow_name == "fleet_sales_admin" else None) or {}
        if not data.get("trip_id"):
            data["trip_id"] = trip_id
        return await _verify_favlogix_and_finalize_balancing(session, clean_p, trip_id, data)

    # 2. Sales Admin clicks [Not Balanced] -> Prompt for collected amount
    if text_lower.startswith("flt_adm_unbal_") or text_lower in {"not balanced", "not balancing", "unbalanced", "2", "2️⃣"}:
        trip_id = text_strip.replace("flt_adm_unbal_", "").strip()
        await set_user_state(
            session,
            clean_p,
            current_step="awaiting_sales_admin_collected_amount",
            current_data={"trip_id": trip_id},
            flow_name="fleet_sales_admin"
        )
        prompt = (
            f"⚖️ *TRANSPORTATION BALANCING: {trip_id}*\n"
            "────────────────────\n"
            "Please enter the actual collected transportation amount in USD:\n"
            "_(e.g. 843.00)_"
        )
        await meta_api.send_text_message(clean_p, prompt)
        return True

    # 3. Active state handling for Sales Admin
    if state and state.flow_name == "fleet_sales_admin":
        if text_lower in {"cancel", "reset", "menu", "back", "exit"}:
            await clear_user_state(session, clean_p)
            await meta_api.send_text_message(clean_p, "Balancing session cancelled.")
            return True

        data = state.current_data or {}
        trip_id = data.get("trip_id", "")
        trip = await get_fleet_trip_request_by_id(session, trip_id)

        # Sales admin enters collected amount -> compare with Favlogix Headless API Trip Report
        if state.current_step == "awaiting_sales_admin_collected_amount":
            clean_val = re.sub(r"[^\d.]", "", text_strip)
            try:
                admin_collected = float(clean_val)
                if admin_collected < 0:
                    raise ValueError()
            except ValueError:
                await meta_api.send_text_message(clean_p, "⚠️ Please enter a valid non-negative number for collected amount (e.g. 843.00):")
                return True

            company_name = trip.company_name if trip else None
            from app.services.favlogix_api_service import favlogix_api_service
            report_data = await favlogix_api_service.get_trip_report_data(trip_id, company_name)

            api_collected = float(report_data.get("collected", 0.0))
            is_matched = abs(api_collected - admin_collected) < 0.01

            if is_matched:
                if trip:
                    trip.status = "BALANCED"
                    trip.discrepancy_amount = 0.0
                    trip.discrepancy_reason = "Balanced against FavLogix report"
                    await session.commit()

                await clear_user_state(session, clean_p)
                ack = (
                    f"✅ *COLLECTIONS MATCH FAVLOGIX RECORD*\n"
                    "────────────────────\n"
                    f"Trip: *{trip_id}*\n"
                    f"FavLogix Collected: *${api_collected:,.2f}*\n"
                    f"Sales Admin Count: *${admin_collected:,.2f}*\n"
                    f"Variance: *$0.00* (Balanced)\n"
                    "────────────────────\n"
                    "Transportation charges are confirmed balanced.\n\n"
                    "Tap below to close this trip:"
                )
                buttons = [
                    {"id": f"flt_adm_close_{trip_id}", "title": "Close Trip"}
                ]
                await meta_api.send_button_message(
                    to_phone=clean_p,
                    body_text=ack,
                    buttons=buttons,
                    header_text="CLOSE TRIP"
                )
                return True
            else:
                # Discrepancy detected: store difference and instruct Sales Admin to update FavLogix
                diff = round(api_collected - admin_collected, 2)
                await set_user_state(
                    session,
                    clean_p,
                    current_step="awaiting_favlogix_update_confirm",
                    current_data={
                        "trip_id": trip_id,
                        "admin_collected": admin_collected,
                        "initial_favlogix_collected": api_collected,
                        "initial_diff": diff
                    },
                    flow_name="fleet_sales_admin"
                )

                discrepancy_msg = (
                    f"⚠️ *DISCREPANCY DETECTED: {trip_id}*\n"
                    "────────────────────\n"
                    f"• FavLogix System Collected: *${api_collected:,.2f}*\n"
                    f"• Driver Physical Collected: *${admin_collected:,.2f}*\n"
                    f"• Discrepancy Difference: *${abs(diff):,.2f}*\n"
                    "────────────────────\n"
                    f"⚠️ Physical collection from driver does not match FavLogix system record.\n\n"
                    f"Please update the FavLogix system so the collected amount is *${admin_collected:,.2f}*.\n\n"
                    "Once updated in FavLogix, tap the *Updated* button below to re-verify:"
                )
                buttons = [
                    {"id": f"flt_adm_fav_updated_{trip_id}", "title": "Updated"}
                ]
                await meta_api.send_button_message(
                    to_phone=clean_p,
                    body_text=discrepancy_msg,
                    buttons=buttons,
                    header_text="UPDATE FAVLOGIX"
                )
                return True

        # Sales admin in awaiting_favlogix_update_confirm triggers verification via button or text
        if state.current_step == "awaiting_favlogix_update_confirm":
            return await _verify_favlogix_and_finalize_balancing(session, clean_p, trip_id, data)

    return False


async def _verify_favlogix_and_finalize_balancing(session: AsyncSession, clean_p: str, trip_id: str, data: Dict[str, Any]) -> bool:
    """Re-queries FavLogix after Sales Admin updates it, adds difference to Sales Rep ledger on match, and offers Close Trip."""
    trip = await get_fleet_trip_request_by_id(session, trip_id)
    if not trip:
        await meta_api.send_text_message(clean_p, f"⚠️ Trip '{trip_id}' not found.")
        return True

    admin_collected = float(data.get("admin_collected", 0.0))
    initial_diff = float(data.get("initial_diff", 0.0))
    initial_favlogix = float(data.get("initial_favlogix_collected", 0.0))

    company_name = trip.company_name if trip else None
    from app.services.favlogix_api_service import favlogix_api_service
    report_data = await favlogix_api_service.get_trip_report_data(trip_id, company_name)
    new_api_collected = float(report_data.get("collected", 0.0))

    is_matched = abs(new_api_collected - admin_collected) < 0.01

    if not is_matched:
        # Still not matching
        still_unmatched_msg = (
            f"❌ *FAVLOGIX NOT MATCHING YET: {trip_id}*\n"
            "────────────────────\n"
            f"• Driver Physical Count: *${admin_collected:,.2f}*\n"
            f"• Current FavLogix Record: *${new_api_collected:,.2f}*\n"
            "────────────────────\n"
            f"FavLogix still shows *${new_api_collected:,.2f}* instead of *${admin_collected:,.2f}*.\n\n"
            "Please ensure the trip report is saved in FavLogix, then tap *Updated* again:"
        )
        buttons = [
            {"id": f"flt_adm_fav_updated_{trip_id}", "title": "Updated"}
        ]
        await meta_api.send_button_message(
            to_phone=clean_p,
            body_text=still_unmatched_msg,
            buttons=buttons,
            header_text="NOT MATCHING"
        )
        return True
    else:
        # IT MATCHES!
        diff_to_add = initial_diff
        from app.database import record_pending_ledger_entry, get_sales_rep_pending_balance

        sales_rep_phone = clean_phone(trip.salesperson_phone) if trip and trip.salesperson_phone else None
        sales_rep_name = trip.salesperson_name if trip else "Sales Representative"

        new_balance = 0.0
        if sales_rep_phone and abs(diff_to_add) > 0.001:
            entry_type = "DEFICIT" if diff_to_add > 0 else "SURPLUS"
            notes = f"FavLogix collection discrepancy adjustment for Trip {trip_id} (FavLogix originally ${initial_favlogix:,.2f} vs Driver collected ${admin_collected:,.2f})"
            await record_pending_ledger_entry(
                session=session,
                phone=sales_rep_phone,
                name=sales_rep_name,
                trip_id=trip_id,
                entry_type=entry_type,
                amount=diff_to_add,
                notes=notes
            )
            new_balance = await get_sales_rep_pending_balance(session, sales_rep_phone)

            # Notify Sales Rep of their updated pending amount
            rep_alert = (
                f"⚖️ *PENDING BALANCE ADJUSTMENT*\n"
                "────────────────────\n"
                f"Trip: *{trip_id}*\n"
                f"Company: *{trip.company_name or 'Tagoneswa Fleet'}*\n"
                f"Discrepancy Added: *${abs(diff_to_add):,.2f}* ({entry_type})\n"
                f"New Net Pending Balance: *${new_balance:,.2f}*\n"
                "────────────────────\n"
                f"Note: Recorded after FavLogix collection reconciliation for Trip {trip_id}."
            )
            from app.handlers.fleet_approval_handler import get_solo_test_mode
            is_solo = get_solo_test_mode()
            targets = [clean_phone(settings.master_admin_phone)] if is_solo else ([sales_rep_phone] if sales_rep_phone else [clean_phone(settings.master_admin_phone)])
            for rep_p in set(targets):
                if rep_p:
                    try:
                        await meta_api.send_text_message(rep_p, rep_alert)
                        logger.info(f"Dispatched pending balance adjustment notice to {rep_p} for {trip_id}")
                    except Exception as ex:
                        logger.warning(f"Could not notify sales rep {rep_p}: {ex}")

        # Update trip in DB
        if trip:
            trip.status = "BALANCED"
            trip.discrepancy_amount = diff_to_add
            trip.discrepancy_reason = f"FavLogix reconciled to ${admin_collected:,.2f}; diff ${diff_to_add:,.2f} added to sales rep pending ledger"
            await session.commit()

        await clear_user_state(session, clean_p)

        # Send confirmation & Close Trip button to Sales Admin
        success_msg = (
            f"✅ *FAVLOGIX UPDATE CONFIRMED*\n"
            "────────────────────\n"
            f"Trip: *{trip_id}*\n"
            f"• Verified FavLogix Collected: *${new_api_collected:,.2f}*\n"
            f"• Driver Physical Count: *${admin_collected:,.2f}*\n"
            f"• Discrepancy Added to Rep Pending: *${abs(diff_to_add):,.2f}*\n"
            "────────────────────\n"
            "Transportation charges are now balanced.\n\n"
            "Tap below to officially close this trip:"
        )
        buttons = [
            {"id": f"flt_adm_close_{trip_id}", "title": "Close Trip"}
        ]
        await meta_api.send_button_message(
            to_phone=clean_p,
            body_text=success_msg,
            buttons=buttons,
            header_text="CLOSE TRIP"
        )
        return True
