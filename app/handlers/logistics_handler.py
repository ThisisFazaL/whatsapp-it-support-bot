import logging
import re
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import (
    FleetTripRequest,
    get_fleet_trip_request_by_id,
    get_pending_trips_for_edward
)
from app.state_manager import set_user_state, clear_user_state, get_user_state, normalize_phone_number
from app.meta_api import meta_api

logger = logging.getLogger("logistics_handler")


def clean_phone(phone: Optional[str]) -> str:
    return normalize_phone_number(str(phone or ""))



def is_edward(phone: str) -> bool:
    from app.handlers.fleet_approval_handler import get_solo_test_mode
    if get_solo_test_mode():
        return True
    cp = clean_phone(phone)
    edw = clean_phone(settings.edward_phone)
    master = clean_phone(settings.master_admin_phone)
    fleet_admin = clean_phone(settings.fleet_admin_phone)
    return cp in {edw, master, fleet_admin}


async def resolve_truck_from_db(session: AsyncSession, query: str):
    """
    Resolves and verifies a truck from the workshop_trucks database table.
    Supports plate number (e.g. 'AGZ 7331', 'agz7331'), truck fleet number ('7331'), or model.
    """
    search_query = (query or "").strip()
    if not search_query:
        return None

    try:
        from app.workshop.models import WorkshopTruck
        clean_query = re.sub(r"[\s#-]", "", search_query).upper()
        digits = re.findall(r"\d+", search_query)
        digit_str = digits[0] if digits else clean_query

        stmt = select(WorkshopTruck).where(WorkshopTruck.active == True)
        res = await session.execute(stmt)
        trucks = res.scalars().all()

        # 1. Exact normalized plate match (e.g. 'AGZ7331' == 'AGZ7331')
        for t in trucks:
            t_clean = re.sub(r"[\s#-]", "", t.plate_number).upper()
            if t_clean == clean_query or search_query.upper() == t.plate_number.upper():
                return t

        # 2. Exact or substring truck_number match (e.g. '7331' matches '7331')
        for t in trucks:
            t_num = str(t.truck_number or "").strip()
            if t_num and (t_num == digit_str or digit_str == t_num or digit_str in t_num):
                return t

        # 3. Substring in plate
        for t in trucks:
            t_clean = re.sub(r"[\s#-]", "", t.plate_number).upper()
            if clean_query in t_clean or t_clean in clean_query:
                return t

        # 4. Model make match
        for t in trucks:
            if clean_query.lower() in (t.model_make or "").lower():
                return t
    except Exception as e:
        logger.warning(f"Error resolving truck from WorkshopTruck: {e}")

    return None


async def resolve_driver_from_db(session: AsyncSession, query: str) -> Optional[Tuple[str, str]]:
    """
    Resolves and verifies a commercial driver from WorkshopStaff or Employee registry.
    Returns (official_full_name, clean_phone) if verified, else None.
    """
    clean_query = (query or "").strip()
    if not clean_query:
        return None

    # 1. Match WorkshopStaff (drivers)
    try:
        from app.workshop.models import WorkshopStaff
        stmt = select(WorkshopStaff).where(WorkshopStaff.active == True)
        res = await session.execute(stmt)
        all_staff = res.scalars().all()

        # Exact match
        for s in all_staff:
            if s.full_name.lower() == clean_query.lower():
                return s.full_name, clean_phone(s.phone)

        # Substring match
        for s in all_staff:
            if clean_query.lower() in s.full_name.lower():
                return s.full_name, clean_phone(s.phone)

        # Token match (e.g. "Terrence" matches "Terrence Mupfumi" or "Kadungure" matches "Godknows Kadungure")
        tokens = [tok.lower() for tok in clean_query.split() if len(tok) >= 3]
        for s in all_staff:
            s_tokens = s.full_name.lower().split()
            if any(tok in s_tokens or any(tok in st for st in s_tokens) for tok in tokens):
                return s.full_name, clean_phone(s.phone)
    except Exception as e:
        logger.warning(f"Error resolving driver from WorkshopStaff: {e}")

    # 2. Match Employee table
    try:
        from app.database import Employee
        stmt_emp = select(Employee).where(Employee.active == True)
        res_emp = await session.execute(stmt_emp)
        all_emps = res_emp.scalars().all()

        for emp in all_emps:
            if emp.full_name.lower() == clean_query.lower():
                return emp.full_name, clean_phone(emp.phone)

        for emp in all_emps:
            if clean_query.lower() in emp.full_name.lower():
                return emp.full_name, clean_phone(emp.phone)

        tokens = [tok.lower() for tok in clean_query.split() if len(tok) >= 3]
        for emp in all_emps:
            emp_tokens = emp.full_name.lower().split()
            if any(tok in emp_tokens or any(tok in et for et in emp_tokens) for tok in tokens):
                return emp.full_name, clean_phone(emp.phone)
    except Exception as e:
        logger.warning(f"Error resolving driver from Employee: {e}")

    return None


async def resolve_driver_phone(session: AsyncSession, driver_name: str) -> Optional[str]:
    """Auto-resolves a driver's WhatsApp phone number from WorkshopStaff or Employee registry."""
    res = await resolve_driver_from_db(session, driver_name)
    return res[1] if res else None


async def notify_edward_new_trip(session: AsyncSession, trip_id: str):
    """
    Sends trip allocation notification to Edward.
    CRITICAL: Sales Total is strictly HIDDEN from Edward!
    """
    trip = await get_fleet_trip_request_by_id(session, trip_id)
    if not trip:
        return

    from app.handlers.fleet_approval_handler import get_solo_test_mode
    is_solo = get_solo_test_mode()
    edw_phone = clean_phone(settings.edward_phone)
    header = "NEW TRIP DISPATCH"
    tag = "🎭 *[SOLO TEST: SIMULATING EDWARD]*\n" if is_solo else ""
    body = (
        f"{tag}NEW TRIP DISPATCH ALLOCATION\n"
        "────────────────────\n"
        f"Company: {trip.company_name}\n"
        f"Trip: {trip.trip_id}\n"
        f"Route: {trip.route or trip.destination_city}\n"
        f"Sales Rep: {trip.salesperson_name or 'Sales'} (+{trip.salesperson_phone})\n"
        "────────────────────\n"
        "Please allocate vehicle and driver details below:"
    )
    footer = "Select an option"
    buttons = [
        {"id": f"flt_edw_alloc_{trip.trip_id}", "title": "Allocate Trip"},
        {"id": "flt_edw_queue", "title": "Trip Queue"}
    ]

    # In solo mode, deliver to Master Admin and the testing Sales Rep
    tester_phones = {clean_phone(settings.master_admin_phone)}
    if trip.salesperson_phone:
        tester_phones.add(clean_phone(trip.salesperson_phone))

    recipients = tester_phones if is_solo else {edw_phone}
    if not is_solo and getattr(settings, "test_user_role", "").upper() == "EDWARD":
        recipients.update(tester_phones)


    for r in recipients:
        if r:
            await meta_api.send_button_message(
                to_phone=r,
                body_text=body,
                buttons=buttons,
                header_text=header,
                footer_text=footer
            )
    logger.info(f"Delivered Stage 3 trip notification for {trip_id} to Edward ({edw_phone})")


async def send_edward_queue(session: AsyncSession, phone: str):
    """Presents Edward with multi-trip FIFO queue selector."""
    clean_p = clean_phone(phone)
    pending = await get_pending_trips_for_edward(session)
    if not pending:
        await meta_api.send_text_message(
            clean_p,
            "✅ *No Pending Trips*\n────────────────────\nAll trip allocation requests have been processed!"
        )
        return

    lines = []
    buttons = []
    trip_ids = [t.trip_id for t in pending]
    for idx, t in enumerate(pending[:3], start=1):
        lines.append(f"{idx}. *{t.trip_id}* | {t.company_name} | {t.route or t.destination_city or 'Depot'}")
        # Button title strictly <= 20 chars, NO emojis, unique
        btn_title = f"{idx}. {t.trip_id}"
        if len(btn_title) > 20:
            btn_title = f"Allocate #{idx}"
        buttons.append({"id": f"flt_edw_alloc_{t.trip_id}", "title": btn_title})

    queue_text = "\n".join(lines)
    body = (
        f"📋 *PENDING TRIPS QUEUE ({len(pending)})*\n"
        "────────────────────\n"
        f"{queue_text}\n"
        "────────────────────\n"
        "Select a trip to allocate by tapping below or replying with its number (1, 2, or 3):"
    )

    await set_user_state(
        session,
        clean_p,
        current_step="awaiting_queue_selection",
        current_data={"pending_trip_ids": trip_ids},
        flow_name="fleet_edward"
    )

    await meta_api.send_button_message(
        to_phone=clean_p,
        body_text=body,
        buttons=buttons,
        header_text="TRIP QUEUE"
    )



async def prompt_truck_plate(session: AsyncSession, phone: str, trip_id: str):
    """Step 1: Edward types truck plate (NO buttons)."""
    trip = await get_fleet_trip_request_by_id(session, trip_id)
    if not trip:
        await meta_api.send_text_message(phone, f"⚠️ Trip {trip_id} not found.")
        return

    await set_user_state(
        session,
        phone,
        current_step="awaiting_truck_plate",
        current_data={"trip_id": trip_id},
        flow_name="fleet_edward"
    )
    prompt = (
        f"🚛 *ALLOCATE VEHICLE: {trip_id}*\n"
        "────────────────────\n"
        f"Company: {trip.company_name}\n"
        f"Route: {trip.route or trip.destination_city}\n"
        "────────────────────\n"
        "Please enter the truck plate number or fleet number:\n"
        "_(e.g. 7331 or AGZ 7331)_"
    )
    await meta_api.send_text_message(phone, prompt)


async def handle_edward_interaction(
    session: AsyncSession,
    phone: str,
    message_text: str,
    state: Optional[Any]
) -> bool:
    """
    Handles all interactions for Edward (Stage 3).
    Returns True if handled, False otherwise.
    """
    clean_p = clean_phone(phone)
    text_strip = message_text.strip()
    text_lower = text_strip.lower()

    # 1. Direct Queue button click
    if text_lower in {"flt_edw_queue", "trip queue", "queue"}:
        await send_edward_queue(session, clean_p)
        return True

    # 2. Allocate button click
    if text_lower.startswith("flt_edw_alloc_"):
        trip_id = text_strip.replace("flt_edw_alloc_", "").strip()
        await prompt_truck_plate(session, clean_p, trip_id)
        return True

    # 3. Confirm Allocation button click
    if text_lower.startswith("flt_edw_confirm_"):
        trip_id = text_strip.replace("flt_edw_confirm_", "").strip()
        trip = await get_fleet_trip_request_by_id(session, trip_id)
        if not trip:
            await meta_api.send_text_message(clean_p, f"⚠️ Trip {trip_id} not found.")
            return True

        trip.status = "ASSIGNED"
        trip.allowance_status = "PENDING_APPROVAL"
        await session.commit()
        await clear_user_state(session, clean_p)

        ack = (
            f"✅ *ALLOCATION CONFIRMED: {trip_id}*\n"
            "────────────────────\n"
            f"Truck: {trip.truck_plate}\n"
            f"Driver: {trip.driver_name}\n"
            f"Total Allowance: ${trip.total_allowance:,.2f}\n"
            "────────────────────\n"
            "Forwarded to Zayn for allowance approval!"
        )
        await meta_api.send_text_message(clean_p, ack)

        # Notify Zayn for Stage 4 approval
        from app.handlers.zayn_accounts_handler import notify_zayn_allowance_approval
        await notify_zayn_allowance_approval(session, trip.trip_id)
        return True

    # 4. Change Allocation button click
    if text_lower.startswith("flt_edw_change_"):
        trip_id = text_strip.replace("flt_edw_change_", "").strip()
        await prompt_truck_plate(session, clean_p, trip_id)
        return True

    # 5. Active state handling for Edward
    if state and state.flow_name == "fleet_edward":
        data = state.current_data or {}
        trip_id = data.get("trip_id", "")
        trip = await get_fleet_trip_request_by_id(session, trip_id) if trip_id else None

        if text_lower in {"cancel", "reset", "menu", "back", "exit"}:
            await clear_user_state(session, clean_p)
            await meta_api.send_text_message(clean_p, "Allocation cancelled.")
            return True

        # Step 0: Selection from Pending Trip Queue (e.g. user replies "1", "2", "3" or types trip ID)
        if state.current_step == "awaiting_queue_selection":
            pending_ids = data.get("pending_trip_ids", [])
            chosen_trip_id = None
            clean_digits = re.sub(r"[^\d]", "", text_strip)
            if clean_digits.isdigit():
                idx = int(clean_digits) - 1
                if 0 <= idx < len(pending_ids):
                    chosen_trip_id = pending_ids[idx]
            if not chosen_trip_id:
                for tid in pending_ids:
                    if text_strip.upper() == tid.upper():
                        chosen_trip_id = tid
                        break
            if chosen_trip_id:
                await prompt_truck_plate(session, clean_p, chosen_trip_id)
                return True
            else:
                await meta_api.send_text_message(
                    clean_p,
                    f"⚠️ Please select a valid trip number (1 to {len(pending_ids)}) or tap one of the buttons."
                )
                return True

        # Step 1: Truck Plate entered & verified against database
        if state.current_step == "awaiting_truck_plate":
            from app.workshop.models import WorkshopTruck
            truck_check = await session.execute(select(WorkshopTruck.truck_id).where(WorkshopTruck.active == True).limit(1))
            has_trucks_in_db = bool(truck_check.scalars().first())

            verified_truck = await resolve_truck_from_db(session, text_strip)
            if verified_truck:
                truck_plate = verified_truck.plate_number
                data["truck_plate"] = truck_plate
                data["truck_model"] = verified_truck.model_make
                await set_user_state(session, clean_p, "awaiting_driver_name", data, flow_name="fleet_edward")
                prompt = (
                    f"👤 *DRIVER ALLOCATION: {trip_id}*\n"
                    f"Truck: *{truck_plate}* ({verified_truck.model_make})\n"
                    "────────────────────\n"
                    "Please enter the commercial driver's name:\n"
                    "_(e.g. Terrence Mupfumi or Godknows)_"
                )
                await meta_api.send_text_message(clean_p, prompt)
                return True
            elif has_trucks_in_db:
                # Truck plate not found in database!
                await meta_api.send_text_message(
                    clean_p,
                    f"⚠️ *Vehicle '{text_strip}' not found in fleet database.*\n\n"
                    "Please enter a valid fleet truck number or plate (e.g. *7331* or *AGZ 7331*):"
                )
                return True
            else:
                # Fallback in mock unit test environments without seeded WorkshopTruck
                truck_plate = text_strip.upper()
                data["truck_plate"] = truck_plate
                await set_user_state(session, clean_p, "awaiting_driver_name", data, flow_name="fleet_edward")
                prompt = (
                    f"👤 *DRIVER ALLOCATION: {trip_id}*\n"
                    f"Truck: *{truck_plate}*\n"
                    "────────────────────\n"
                    "Please type the driver's full name:\n"
                    "_(e.g. Terrence Mupfumi)_"
                )
                await meta_api.send_text_message(clean_p, prompt)
                return True

        # Step 2: Driver Name entered & verified against database -> Auto-resolve phone & hand off to Sales Rep
        if state.current_step == "awaiting_driver_name":
            from app.workshop.models import WorkshopStaff
            staff_check = await session.execute(select(WorkshopStaff.staff_id).where(WorkshopStaff.active == True).limit(1))
            has_staff_in_db = bool(staff_check.scalars().first())

            driver_info = await resolve_driver_from_db(session, text_strip)
            if driver_info:
                driver_name, driver_phone = driver_info
            elif has_staff_in_db:
                # Driver not found in database!
                await meta_api.send_text_message(
                    clean_p,
                    f"⚠️ *Driver '{text_strip}' not found in database.*\n\n"
                    "Please enter the name of a registered commercial driver (e.g. *Terrence Mupfumi*, *Godknows Kadungure*, *Wilbert Makoma*):"
                )
                return True
            else:
                driver_name = text_strip.title()
                driver_phone = await resolve_driver_phone(session, driver_name)

            truck_plate = data.get("truck_plate", "")
            if trip:
                trip.truck_plate = truck_plate
                trip.driver_name = driver_name
                trip.driver_phone = driver_phone
                trip.status = "ALLOCATED"
                await session.commit()

            await clear_user_state(session, clean_p)

            ph_display = f" (+{driver_phone})" if driver_phone else ""
            sales_name = trip.salesperson_name if trip else "Sales"
            ack = (
                f"✅ *DISPATCH ALLOCATED: {trip_id}*\n"
                "────────────────────\n"
                f"Truck: {truck_plate}\n"
                f"Driver: {driver_name}{ph_display}\n"
                "────────────────────\n"
                f"Handoff sent to Sales Rep ({sales_name}) to enter schedule & allowances!"
            )
            await meta_api.send_text_message(clean_p, ack)

            # Handoff immediately to Sales Rep for crew, departure, return, and allowance calculation
            from app.handlers.fleet_approval_handler import notify_sales_rep_allowance_entry
            await notify_sales_rep_allowance_entry(session, trip_id)
            return True

        # Step 3: Driver Phone entered
        if state.current_step == "awaiting_driver_phone":
            drv_phone = clean_phone(text_strip)
            if not drv_phone or len(drv_phone) < 9:
                await meta_api.send_text_message(clean_p, "⚠️ Please enter a valid phone number (digits only, at least 9 digits):")
                return True
            data["driver_phone"] = drv_phone
            await set_user_state(session, clean_p, "awaiting_crew_count", data, flow_name="fleet_edward")
            # NO brackets in prompt as requested!
            prompt = (
                f"👥 *CREW ALLOCATION: {trip_id}*\n"
                "────────────────────\n"
                "Enter number of crew members:\n"
                "_(type number, e.g. 2)_"
            )
            await meta_api.send_text_message(clean_p, prompt)
            return True

        # Step 4: Crew Count entered
        if state.current_step == "awaiting_crew_count":
            digits = re.sub(r"[^\d]", "", text_strip)
            try:
                crew_count = int(digits)
                if crew_count <= 0:
                    raise ValueError()
            except ValueError:
                await meta_api.send_text_message(clean_p, "⚠️ Please enter a valid number of crew members (e.g. 2):")
                return True

            data["crew_count"] = crew_count
            await set_user_state(session, clean_p, "awaiting_meal_count", data, flow_name="fleet_edward")
            # NO brackets in prompt as requested!
            prompt = (
                f"🍱 *MEAL ALLOCATION: {trip_id}*\n"
                "────────────────────\n"
                "Enter number of meals per person:\n"
                "_(type number, e.g. 3)_"
            )
            await meta_api.send_text_message(clean_p, prompt)
            return True

        # Step 5: Meal Count entered
        if state.current_step == "awaiting_meal_count":
            digits = re.sub(r"[^\d]", "", text_strip)
            try:
                meal_count = int(digits)
                if meal_count <= 0:
                    raise ValueError()
            except ValueError:
                await meta_api.send_text_message(clean_p, "⚠️ Please enter a valid number of meals (e.g. 3):")
                return True

            data["meal_count"] = meal_count
            await set_user_state(session, clean_p, "awaiting_toll_count", data, flow_name="fleet_edward")
            prompt = (
                f"🛣️ *TOLL GATES: {trip_id}*\n"
                "────────────────────\n"
                "Enter number of tolls on route:\n"
                "_(type number, e.g. 4)_"
            )
            await meta_api.send_text_message(clean_p, prompt)
            return True

        # Step 6: Tolls Count entered
        if state.current_step == "awaiting_toll_count":
            digits = re.sub(r"[^\d]", "", text_strip)
            try:
                toll_count = int(digits)
                if toll_count < 0:
                    raise ValueError()
            except ValueError:
                await meta_api.send_text_message(clean_p, "⚠️ Please enter a valid number of tolls (e.g. 4 or 0):")
                return True

            data["toll_gates_count"] = toll_count
            await set_user_state(session, clean_p, "awaiting_toll_cost", data, flow_name="fleet_edward")
            prompt = (
                f"💵 *TOLL COST: {trip_id}*\n"
                "────────────────────\n"
                "Enter total toll cost in USD:\n"
                "_(e.g. 34.50 or 0)_"
            )
            await meta_api.send_text_message(clean_p, prompt)
            return True

        # Step 7: Toll Cost entered -> Compute & Present Review Summary
        if state.current_step == "awaiting_toll_cost":
            clean_val = re.sub(r"[^\d.]", "", text_strip)
            try:
                toll_cost = float(clean_val)
                if toll_cost < 0:
                    raise ValueError()
            except ValueError:
                await meta_api.send_text_message(clean_p, "⚠️ Please enter a valid toll cost in USD (e.g. 34.50):")
                return True

            crew_count = int(data.get("crew_count", 2))
            meal_count = int(data.get("meal_count", 3))
            toll_gates_count = int(data.get("toll_gates_count", 0))
            food_allowance = round(2.0 * crew_count * meal_count, 2)
            total_allowance = round(toll_cost + food_allowance, 2)

            truck_plate = data.get("truck_plate", "")
            driver_name = data.get("driver_name", "")
            driver_phone = data.get("driver_phone", "")

            # Update Trip Request record
            if trip:
                trip.truck_plate = truck_plate
                trip.driver_name = driver_name
                trip.driver_phone = driver_phone
                trip.crew_count = crew_count
                trip.meal_count = meal_count
                trip.toll_gates_count = toll_gates_count
                trip.toll_cost = toll_cost
                trip.food_allowance = food_allowance
                trip.total_allowance = total_allowance
                await session.commit()

            # Review Card with Confirm & Change buttons (NO emojis on buttons!)
            header = "TRIP ALLOCATION"
            body = (
                "TRIP ALLOCATION SUMMARY\n"
                "────────────────────\n"
                f"Company: {trip.company_name if trip else 'Tagoneswa'}\n"
                f"Trip: {trip_id} | Route: {trip.route if trip else ''}\n"
                f"Driver: {driver_name} | Truck: {truck_plate}\n"
                f"Crew: {crew_count} people | Meals: {meal_count} | Tolls: {toll_gates_count}\n"
                "────────────────────\n"
                f"Toll cost: ${toll_cost:,.2f}\n"
                f"Food ($2 x {crew_count} x {meal_count}): ${food_allowance:,.2f}\n"
                "────────────────────\n"
                f"Total allowance: ${total_allowance:,.2f}\n"
                "Please confirm or change:"
            )
            buttons = [
                {"id": f"flt_edw_confirm_{trip_id}", "title": "Confirm"},
                {"id": f"flt_edw_change_{trip_id}", "title": "Change"}
            ]
            await meta_api.send_button_message(
                to_phone=clean_p,
                body_text=body,
                buttons=buttons,
                header_text=header
            )
            return True

    return False
