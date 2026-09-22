import datetime
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.meta_api import meta_api
from app.state_manager import set_user_state, clear_user_state
from app.workshop.models import WorkshopStaff, WorkshopTicket, WorkshopTruck

async def get_ticket_with_truck(session: AsyncSession, ticket_id: int = None) -> WorkshopTicket:
    if ticket_id:
        stmt = select(WorkshopTicket).options(selectinload(WorkshopTicket.truck)).where(WorkshopTicket.ticket_id == ticket_id)
        t = (await session.execute(stmt)).scalars().first()
        if t:
            return t
    stmt_latest = select(WorkshopTicket).options(selectinload(WorkshopTicket.truck)).order_by(WorkshopTicket.ticket_id.desc())
    return (await session.execute(stmt_latest)).scalars().first()

async def handle_supervisor_action(session: AsyncSession, staff: WorkshopStaff, message_text: str, data: dict, state_step: str = None):
    phone = staff.phone
    text = (message_text or "").strip()
    is_btn = text.startswith("btn_")
    
    # 1. State: Entering Reject Reason
    if state_step == "ws_reject_reason" and not is_btn:
        ticket_id = data.get("ticket_id")
        ticket = await get_ticket_with_truck(session, ticket_id)
        if ticket:
            ticket.status = "CLOSED"
            ticket.internal_outcome = "NO_VALID_FAULT"
            ticket.internal_action_notes = text
            await session.commit()
            await clear_user_state(session, phone)
            
            # Confirm to Supervisor
            await meta_api.send_text_message(
                phone,
                f"✅ Ticket `{ticket.ticket_number}` has been rejected and closed.\n📝 *Reason:* {text}"
            )
            
            # NOTIFY TICKET RAISER (Driver / Logistics Assistant)
            if ticket.logged_by_staff_id:
                raiser = await session.get(WorkshopStaff, ticket.logged_by_staff_id)
                if raiser:
                    truck_num = ticket.truck.truck_number if ticket.truck else ""
                    truck_model = ticket.truck.model_make if ticket.truck else ""
                    raiser_msg = (
                        f"🚫 *Workshop Fault Ticket Closed (Rejected)*\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🎫 *Ticket ID:* `{ticket.ticket_number}`\n"
                        f"🚚 *Vehicle:* Truck #{truck_num} ({truck_model})\n"
                        f"👤 *Reviewed By:* {staff.full_name} (Supervisor)\n"
                        f"📝 *Reason:* {text}\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"⚠️ *Status: CLOSED (No Valid Fault Found)*."
                    )
                    await meta_api.send_text_message(
                        raiser.phone,
                        raiser_msg,
                        fallback_template="workshop_fleet_ready",
                        template_params=[raiser.full_name, ticket.ticket_number, f"Truck #{truck_num}"]
                    )
        return True

    # 2. State: Entering Internal Fix Notes
    if state_step == "ws_internal_fix_notes" and not is_btn:
        ticket_id = data.get("ticket_id")
        ticket = await get_ticket_with_truck(session, ticket_id)
        if ticket:
            ticket.status = "CLOSED"
            ticket.internal_outcome = "RESOLVED_INTERNALLY"
            ticket.internal_action_notes = text
            await session.commit()
            await clear_user_state(session, phone)
            
            # Confirm to Supervisor
            await meta_api.send_text_message(
                phone,
                f"✅ Ticket `{ticket.ticket_number}` resolved internally and closed.\n📝 *Action Taken:* {text}"
            )
            
            # NOTIFY TICKET RAISER (Driver / Logistics Assistant)
            if ticket.logged_by_staff_id:
                raiser = await session.get(WorkshopStaff, ticket.logged_by_staff_id)
                if raiser:
                    truck_num = ticket.truck.truck_number if ticket.truck else ""
                    truck_model = ticket.truck.model_make if ticket.truck else ""
                    raiser_msg = (
                        f"🛠️ *Workshop Fault Resolved Internally*\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🎫 *Ticket ID:* `{ticket.ticket_number}`\n"
                        f"🚚 *Vehicle:* Truck #{truck_num} ({truck_model})\n"
                        f"👤 *Resolved By:* {staff.full_name} (Supervisor)\n"
                        f"📝 *Action Taken:* {text}\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"✅ *Status: CLOSED (Resolved Internally)*. Vehicle is operational."
                    )
                    await meta_api.send_text_message(
                        raiser.phone,
                        raiser_msg,
                        fallback_template="workshop_fleet_ready",
                        template_params=[raiser.full_name, ticket.ticket_number, f"Truck #{truck_num}"]
                    )
        return True

    # 3. State: Entering QC Failure Reason (Rework Loop)
    if state_step == "ws_qc_fail_reason" and not is_btn:
        ticket_id = data.get("ticket_id")
        ticket = await get_ticket_with_truck(session, ticket_id)
        if ticket:
            ticket.status = "REWORK_REQUIRED"
            ticket.qc_passed = False
            ticket.qc_failure_reason = text
            ticket.qc_tested_at = datetime.datetime.utcnow()
            await session.commit()
            await clear_user_state(session, phone)
            
            await meta_api.send_text_message(
                phone,
                f"⚠️ Ticket `{ticket.ticket_number}` marked *REWORK REQUIRED*.\n📝 *Failure Notes:* {text}\n\nAlert sent to mechanic to re-fix on shop floor."
            )
            
            if ticket.assigned_mechanic_id:
                mechanic = await session.get(WorkshopStaff, ticket.assigned_mechanic_id)
                if mechanic:
                    truck_num = ticket.truck.truck_number if ticket.truck else ""
                    rework_alert = (
                        f"⚠️ *QC TEST FAILED — REWORK REQUIRED*\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🎫 *Ticket ID:* `{ticket.ticket_number}`\n"
                        f"🚚 *Vehicle:* Truck #{truck_num}\n"
                        f"📝 *QC Failure Reason from Edward:* {text}\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"Please inspect and fix again. Tap completion when done."
                    )
                    buttons = [{"id": f"btn_ws_repair_done_{ticket.ticket_id}", "title": "🏁 Repair Completed"}]
                    await meta_api.send_button_message(mechanic.phone, rework_alert, buttons, header_text="REWORK ALERT")
        return True

    # Button Clicks (Handles both button ID and title text)
    if text.startswith("btn_ws_route_intern_") or "handle internally" in text.lower():
        ticket_id = int(text.split("_")[-1]) if text.startswith("btn_ws_route_intern_") else None
        ticket = await get_ticket_with_truck(session, ticket_id)
        t_id = ticket.ticket_id if ticket else 1
        t_num = ticket.ticket_number if ticket else "Current Job"
        
        body = f"🛠️ *Internal Handling for Ticket `{t_num}`*\n\nPlease select the outcome:"
        buttons = [
            {"id": f"btn_ws_resolve_intern_{t_id}", "title": "✅ Resolved Internally"},
            {"id": f"btn_ws_reject_{t_id}", "title": "❌ No Valid Fault"}
        ]
        await meta_api.send_button_message(phone, body, buttons, header_text="INTERNAL ACTION")
        return True

    if text.startswith("btn_ws_resolve_intern_") or "resolved internally" in text.lower():
        ticket_id = int(text.split("_")[-1]) if text.startswith("btn_ws_resolve_intern_") else None
        ticket = await get_ticket_with_truck(session, ticket_id)
        t_id = ticket.ticket_id if ticket else 1
        await set_user_state(session, phone, "ws_internal_fix_notes", {"ticket_id": t_id})
        await meta_api.send_text_message(phone, "📝 Please record the action taken to resolve this internally:")
        return True

    if text.startswith("btn_ws_reject_") or "no valid fault" in text.lower() or "reject" in text.lower():
        ticket_id = int(text.split("_")[-1]) if text.startswith("btn_ws_reject_") else None
        ticket = await get_ticket_with_truck(session, ticket_id)
        t_id = ticket.ticket_id if ticket else 1
        await set_user_state(session, phone, "ws_reject_reason", {"ticket_id": t_id})
        await meta_api.send_text_message(phone, "📝 *Mandatory Closure Reason:*\nPlease explain why this fault report is invalid or rejected:")
        return True

    if text.startswith("btn_ws_route_work_") or "send to workshop" in text.lower():
        ticket_id = int(text.split("_")[-1]) if text.startswith("btn_ws_route_work_") else None
        ticket = await get_ticket_with_truck(session, ticket_id)
        if ticket:
            stmt = select(WorkshopStaff).where(WorkshopStaff.role == "MECHANIC", WorkshopStaff.active == True)
            mechanic = (await session.execute(stmt)).scalars().first()
            if not mechanic:
                stmt_lead = select(WorkshopStaff).where(WorkshopStaff.role == "LEAD", WorkshopStaff.active == True)
                mechanic = (await session.execute(stmt_lead)).scalars().first()
            
            ticket.assigned_mechanic_id = mechanic.staff_id if mechanic else None
            ticket.status = "WITH_MECHANIC"
            await session.commit()
            
            # Confirm to Supervisor
            await meta_api.send_text_message(
                phone,
                f"✅ Ticket `{ticket.ticket_number}` routed to workshop floor.\n👨‍🔧 *Assigned Mechanic:* {mechanic.full_name if mechanic else 'Workshop Queue'}"
            )
            
            # NOTIFY DRIVER / TICKET RAISER
            if ticket.logged_by_staff_id:
                raiser = await session.get(WorkshopStaff, ticket.logged_by_staff_id)
                if raiser:
                    truck_num = ticket.truck.truck_number if ticket.truck else ""
                    await meta_api.send_text_message(
                        raiser.phone,
                        f"🚚 *Vehicle Status Update*\n"
                        f"🎫 Ticket: `{ticket.ticket_number}` (Truck #{truck_num})\n"
                        f"Status: *APPROVED & SENT TO WORKSHOP*\n"
                        f"👨‍🔧 Assigned Mechanic: *{mechanic.full_name if mechanic else 'Workshop Floor'}*"
                    )
            
            # Alert Mechanic
            if mechanic:
                truck_num = ticket.truck.truck_number if ticket.truck else ""
                truck_model = ticket.truck.model_make if ticket.truck else ""
                
                # Forward driver's defect photo to mechanic
                if ticket.image_id:
                    await meta_api.send_image_message(
                        mechanic.phone,
                        ticket.image_id,
                        caption=f"📸 Driver Defect Photo for Ticket `{ticket.ticket_number}` (Truck #{truck_num})"
                    )
                    
                mech_alert = (
                    f"🔧 *NEW WORKSHOP JOB ASSIGNED*\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🎫 *Ticket ID:* `{ticket.ticket_number}`\n"
                    f"🚚 *Vehicle:* Truck #{truck_num} ({truck_model})\n"
                    f"📌 *Fault:* {ticket.category_name} ➔ {ticket.subcategory_name}\n"
                    f"📝 *Notes:* {ticket.description}\n"
                    f"📸 *Photo:* {'Attached above' if ticket.image_id else 'None'}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"⏱️ *Please enter your Estimated Completion Time (e.g. 'Tomorrow 11 AM' or '2 hours'):*"
                )
                await set_user_state(session, mechanic.phone, "ws_enter_eta", {"ticket_id": ticket.ticket_id})
                await meta_api.send_text_message(
                    mechanic.phone,
                    mech_alert,
                    fallback_template="workshop_job_alert",
                    template_params=[mechanic.full_name, ticket.ticket_number, f"Truck #{truck_num} ({truck_model})", f"{ticket.category_name} - {ticket.subcategory_name}"]
                )
        return True

    if text.startswith("btn_ws_qc_fail_") or "failed" in text.lower() or "rework" in text.lower():
        ticket_id = int(text.split("_")[-1]) if text.startswith("btn_ws_qc_fail_") else None
        ticket = await get_ticket_with_truck(session, ticket_id)
        t_id = ticket.ticket_id if ticket else 1
        await set_user_state(session, phone, "ws_qc_fail_reason", {"ticket_id": t_id})
        await meta_api.send_text_message(phone, "📝 *Mandatory Failure Reason:*\nPlease enter why the vehicle failed QC testing (e.g. 'Brake pedal still soft'):")
        return True

    if text.startswith("btn_ws_qc_pass_") or "passed test" in text.lower():
        ticket_id = int(text.split("_")[-1]) if text.startswith("btn_ws_qc_pass_") else None
        ticket = await get_ticket_with_truck(session, ticket_id)
        if ticket:
            truck_num = ticket.truck.truck_number if ticket.truck else ""
            body = (
                f"✅ Vehicle Passed Quality Testing!\n\n"
                f"🎫 Ticket: `{ticket.ticket_number}`\n"
                f"🚚 Truck: #{truck_num}\n\n"
                f"Ready to return to active fleet?"
            )
            buttons = [{"id": f"btn_ws_return_fleet_{ticket.ticket_id}", "title": "🚀 Return to Fleet"}]
            await meta_api.send_button_message(phone, body, buttons, header_text="CONFIRM FLEET RETURN")
        return True

    if text.startswith("btn_ws_return_fleet_") or "return to fleet" in text.lower():
        ticket_id = int(text.split("_")[-1]) if text.startswith("btn_ws_return_fleet_") else None
        ticket = await get_ticket_with_truck(session, ticket_id)
        if ticket:
            ticket.status = "CLOSED"
            ticket.qc_passed = True
            ticket.return_to_fleet_at = datetime.datetime.utcnow()
            await session.commit()
            await clear_user_state(session, phone)
            
            # Confirm to Supervisor
            await meta_api.send_text_message(
                phone,
                f"🚀 *Vehicle Returned to Fleet!*\n🎫 Ticket `{ticket.ticket_number}` is now *CLOSED*.\nTimestamp recorded."
            )
            
            # NOTIFY DRIVER / TICKET RAISER
            if ticket.logged_by_staff_id:
                driver = await session.get(WorkshopStaff, ticket.logged_by_staff_id)
                if driver:
                    truck_num = ticket.truck.truck_number if ticket.truck else ""
                    driver_msg = (
                        f"✅ *Vehicle Returned to Active Fleet*\n"
                        f"🎫 Ticket: `{ticket.ticket_number}`\n"
                        f"🚚 Truck #{truck_num} passed QC inspection and is ready for dispatch!"
                    )
                    await meta_api.send_text_message(
                        driver.phone,
                        driver_msg,
                        fallback_template="workshop_fleet_ready",
                        template_params=[driver.full_name, ticket.ticket_number, f"Truck #{truck_num}"]
                    )
        return True

    # 3. Supervisor Portal Actions (Active Jobs, Log Defect, Fleet Overview)
    if text == "btn_ws_sup_active_jobs" or text.lower() in {"active jobs", "jobs", "status", "qc jobs"}:
        stmt = select(WorkshopTicket).options(
            selectinload(WorkshopTicket.truck),
            selectinload(WorkshopTicket.assigned_mechanic)
        ).where(WorkshopTicket.status != "CLOSED").order_by(WorkshopTicket.ticket_id.desc())
        active_tickets = (await session.execute(stmt)).scalars().all()
        
        if not active_tickets:
            msg = (
                f"✅ *All Fleet Vehicles Operational*\n\n"
                f"There are currently no open workshop jobs or pending gatekeeper reviews."
            )
            buttons = [
                {"id": "btn_ws_sup_log_defect", "title": "🚛 Log Truck Defect"},
                {"id": "btn_ws_sup_fleet_summary", "title": "📊 Fleet Overview"}
            ]
            await meta_api.send_button_message(phone, msg, buttons, header_text="WORKSHOP JOBS")
            return True
            
        lines = [f"📋 *Active Workshop Jobs ({len(active_tickets)}):*\n"]
        first_actionable_id = None
        first_actionable_type = None
        for t in active_tickets[:5]:
            truck_num = t.truck.truck_number if t.truck else "N/A"
            mech_name = t.assigned_mechanic.full_name if t.assigned_mechanic else "Unassigned"
            status_tag = t.status.replace("_", " ")
            lines.append(f"• 🎫 *{t.ticket_number}* (Truck #{truck_num})\n  📌 Fault: {t.category_name} ➔ {t.subcategory_name}\n  📊 Status: `{status_tag}` | Mechanic: {mech_name}")
            if not first_actionable_id and t.status in ("UNDER_REVIEW", "AWAITING_TEST"):
                first_actionable_id = t.ticket_id
                first_actionable_type = t.status

        buttons = []
        if first_actionable_id:
            title = "🔍 Review Defect" if first_actionable_type == "UNDER_REVIEW" else "🚗 Perform QC Test"
            buttons.append({"id": f"btn_ws_open_ticket_{first_actionable_id}", "title": title})
        buttons.append({"id": "btn_ws_sup_log_defect", "title": "🚛 Log Defect"})
        buttons.append({"id": "btn_ws_sup_fleet_summary", "title": "📊 Fleet Overview"})
        
        await meta_api.send_button_message(phone, "\n".join(lines), buttons[:3], header_text="ACTIVE WORKSHOP JOBS")
        return True

    if text == "btn_ws_sup_log_defect" or text.lower() in {"log defect", "log truck defect", "report defect"}:
        await set_user_state(session, phone, "ws_truck_search", {})
        msg = (
            f"🚚 *Log Truck Defect / Breakdown*\n\n"
            f"Please enter the *Truck Number* (e.g. for plate `AGZ 7331`, type `7331`):"
        )
        await meta_api.send_text_message(phone, msg)
        return True

    if text == "btn_ws_sup_fleet_summary" or text.lower() in {"fleet overview", "fleet summary", "fleet"}:
        trucks = (await session.execute(select(WorkshopTruck))).scalars().all()
        active_tickets = (await session.execute(select(WorkshopTicket).where(WorkshopTicket.status != "CLOSED"))).scalars().all()
        in_workshop = sum(1 for t in active_tickets if t.status in ("WITH_MECHANIC", "REPAIR_IN_PROGRESS", "REWORK_REQUIRED"))
        awaiting_parts = sum(1 for t in active_tickets if t.status == "AWAITING_PARTS")
        awaiting_qc = sum(1 for t in active_tickets if t.status == "AWAITING_TEST")
        under_review = sum(1 for t in active_tickets if t.status == "UNDER_REVIEW")
        operational = len(trucks) - len(active_tickets)
        
        msg = (
            f"📊 *Tagoneswa Fleet Overview*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🚚 *Total Registered Fleet:* {len(trucks)} Trucks\n"
            f"🟢 *Operational on Road:* {max(0, operational)}\n"
            f"🟡 *Under Gatekeeper Review:* {under_review}\n"
            f"🔧 *Active in Workshop:* {in_workshop}\n"
            f"📦 *Awaiting Spare Parts:* {awaiting_parts}\n"
            f"🚗 *Awaiting QC Road-Test:* {awaiting_qc}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"Select action:"
        )
        buttons = [
            {"id": "btn_ws_sup_active_jobs", "title": "🔍 Active Jobs"},
            {"id": "btn_ws_sup_log_defect", "title": "🚛 Log Truck Defect"}
        ]
        await meta_api.send_button_message(phone, msg, buttons, header_text="FLEET OVERVIEW")
        return True

    return False

async def send_supervisor_portal_menu(session: AsyncSession, phone: str, staff: WorkshopStaff, is_start_shift: bool = False):
    """Sends interactive operational menu for Logistics Supervisor."""
    from app.state_manager import clear_user_state
    await clear_user_state(session, phone)
    
    stmt = select(WorkshopTicket).where(WorkshopTicket.status != "CLOSED")
    active_tickets = (await session.execute(stmt)).scalars().all()
    active_count = len(active_tickets)
    
    review_count = sum(1 for t in active_tickets if t.status == "UNDER_REVIEW")
    qc_count = sum(1 for t in active_tickets if t.status == "AWAITING_TEST")
    
    status_summary = []
    if review_count > 0:
        status_summary.append(f"⚠️ *{review_count}* Pending Gatekeeper Review")
    if qc_count > 0:
        status_summary.append(f"🚗 *{qc_count}* Awaiting Road-Test QC")
    if not status_summary:
        status_summary.append(f"📊 *{active_count}* Active in Workshop Floor")
        
    summary_str = "\n".join(status_summary)
    
    if is_start_shift:
        header = "🟢 SHIFT ACTIVE (24H OPEN)"
        msg = (
            f"🌅 *Good Morning, {staff.full_name}!* 🟢\n"
            f"Role: *Logistics Supervisor (Gatekeeper)*\n\n"
            f"Your 24-hour WhatsApp messaging window is now open.\n"
            f"You will receive all vehicle breakdown alerts and QC road-test notifications in real-time.\n\n"
            f"{summary_str}\n\n"
            f"Please select an option below:"
        )
    else:
        header = "SUPERVISOR PORTAL"
        msg = (
            f"👋 *Welcome {staff.full_name}* (Logistics Supervisor)\n"
            f"🚚 *Workshop & Fleet Management Portal*\n\n"
            f"{summary_str}\n\n"
            f"Please select an option below:"
        )
    buttons = [
        {"id": "btn_ws_sup_active_jobs", "title": "🔍 Active Jobs & QC"},
        {"id": "btn_ws_sup_log_defect", "title": "🚛 Log Truck Defect"},
        {"id": "btn_ws_sup_fleet_summary", "title": "📊 Fleet Overview"}
    ]
    await meta_api.send_button_message(phone, msg, buttons, header_text=header)

