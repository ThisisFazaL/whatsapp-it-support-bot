from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.state_manager import get_user_state
from app.workshop.models import WorkshopStaff
from app.workshop.flow_handler import (
    GLOBAL_RESET_KEYWORDS, start_workshop_flow, handle_truck_search,
    handle_truck_confirmation, handle_category_selection, handle_subcategory_selection,
    handle_description_entry, handle_photo_step
)
from app.workshop.supervisor_handler import handle_supervisor_action
from app.workshop.purchasing_handler import handle_purchasing_action
from app.workshop.mechanic_handler import handle_mechanic_action

async def get_workshop_staff(session: AsyncSession, phone: str) -> WorkshopStaff:
    """Checks if the phone number belongs to registered workshop staff with flexible 9-digit suffix matching."""
    if not phone:
        return None
    clean_phone = "".join(filter(str.isdigit, str(phone)))
    last_9 = clean_phone[-9:] if len(clean_phone) >= 9 else clean_phone
    
    stmt = select(WorkshopStaff).where(
        (WorkshopStaff.phone == phone) |
        (WorkshopStaff.phone == clean_phone) |
        (WorkshopStaff.phone.endswith(last_9)),
        WorkshopStaff.active == True
    )
    return (await session.execute(stmt)).scalars().first()

async def handle_workshop_message(session: AsyncSession, staff: WorkshopStaff, message_text: str, image_id: str = None):
    """Main routing entrypoint for all workshop roles."""
    phone = staff.phone
    text = (message_text or "").strip()
    
    # 1. Global Reset / Menu
    if text.lower() in GLOBAL_RESET_KEYWORDS:
        from app.state_manager import clear_user_state
        await clear_user_state(session, phone)
        await start_workshop_flow(session, staff)
        return True

    # 1.2 Open Ticket Details from Template Quick-Reply Button Tap
    if text.startswith("btn_ws_open_ticket_") or text.lower() in {"view ticket & actions", "open ticket details", "view ticket", "open ticket", "view"}:
        ticket_id = None
        if text.startswith("btn_ws_open_ticket_"):
            try:
                ticket_id = int(text.split("_")[-1])
            except Exception:
                ticket_id = None
                
        from app.workshop.models import WorkshopTicket, WorkshopPartsRequest
        from sqlalchemy.orm import selectinload
        
        if ticket_id:
            stmt = select(WorkshopTicket).options(selectinload(WorkshopTicket.truck)).where(WorkshopTicket.ticket_id == ticket_id)
            ticket = (await session.execute(stmt)).scalars().first()
        else:
            # Fetch most recent active ticket for this user's context
            stmt = select(WorkshopTicket).options(selectinload(WorkshopTicket.truck)).order_by(WorkshopTicket.ticket_id.desc())
            ticket = (await session.execute(stmt)).scalars().first()
            
        if ticket:
            truck_num = ticket.truck.truck_number if ticket.truck else ""
            truck_model = ticket.truck.model_make if ticket.truck else ""
            role_u = staff.role.upper()
            from app.meta_api import meta_api
            
            if role_u in {"SUPERVISOR", "LOGISTICS SUPERVISOR", "ADMIN"}:
                if ticket.status == "UNDER_REVIEW":
                    sup_msg = (
                        f"🔍 *GATEKEEPER REVIEW (Ticket {ticket.ticket_number})*\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🚚 *Vehicle:* Truck #{truck_num} ({truck_model})\n"
                        f"📌 *Fault:* {ticket.category_name} ➔ {ticket.subcategory_name}\n"
                        f"📝 *Notes:* {ticket.description}\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"Please select routing action:"
                    )
                    buttons = [
                        {"id": f"btn_ws_route_intern_{ticket.ticket_id}", "title": "🛠️ Handle Internally"},
                        {"id": f"btn_ws_route_work_{ticket.ticket_id}", "title": "🏭 Send to Workshop"}
                    ]
                    await meta_api.send_button_message(phone, sup_msg, buttons, header_text="SUPERVISOR REVIEW")
                    return True
                elif ticket.status == "AWAITING_TEST":
                    qc_alert = (
                        f"🚗 *VEHICLE READY FOR QC TESTING*\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🎫 *Ticket ID:* `{ticket.ticket_number}`\n"
                        f"🚚 *Vehicle:* Truck #{truck_num} ({truck_model})\n"
                        f"⏱️ *SLA:* 🟢 {ticket.sla_result or 'ON_TIME'}\n"
                        f"📝 *Work Done:* {ticket.resolution_notes}\n"
                        f"💵 *Costing:* {ticket.cost_total}\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"Did the vehicle pass inspection & road test?"
                    )
                    buttons = [
                        {"id": f"btn_ws_qc_pass_{ticket.ticket_id}", "title": "✅ Passed Test"},
                        {"id": f"btn_ws_qc_fail_{ticket.ticket_id}", "title": "⚠️ Failed / Rework"}
                    ]
                    await meta_api.send_button_message(phone, qc_alert, buttons, header_text="QC ROAD-TEST")
                    return True
                else:
                    await meta_api.send_text_message(
                        phone,
                        f"🎫 *Ticket {ticket.ticket_number} Status:* `{ticket.status}`\n"
                        f"🚚 *Vehicle:* Truck #{truck_num} ({truck_model})\n"
                        f"📌 *Fault:* {ticket.category_name} ➔ {ticket.subcategory_name}"
                    )
                    return True
                    
            elif role_u in {"PURCHASING", "PROCUREMENT"}:
                stmt_req = select(WorkshopPartsRequest).where(WorkshopPartsRequest.ticket_id == ticket.ticket_id).order_by(WorkshopPartsRequest.request_id.desc())
                parts_req = (await session.execute(stmt_req)).scalars().first()
                if parts_req:
                    p_msg = (
                        f"🛒 *PARTS REQUISITION (Ticket {ticket.ticket_number})*\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🚚 *Vehicle:* Truck #{truck_num} ({truck_model})\n"
                        f"📦 *Part Required:* {parts_req.part_name}\n"
                        f"⏳ *Status:* `{parts_req.status}`\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"Please confirm action:"
                    )
                    buttons = [
                        {"id": f"btn_parts_received_{parts_req.request_id}", "title": "📦 Part Received"},
                        {"id": f"btn_parts_need_info_{parts_req.request_id}", "title": "❓ Need Info/Sample"}
                    ]
                    await meta_api.send_button_message(phone, p_msg, buttons, header_text="PARTS REQUEST")
                    return True
                    
            elif role_u in {"MECHANIC", "LEAD"}:
                if ticket.status == "WITH_MECHANIC":
                    await set_user_state(session, phone, "ws_enter_eta", {"ticket_id": ticket.ticket_id})
                    await meta_api.send_text_message(
                        phone,
                        f"🔧 *JOB DETAILS (Ticket {ticket.ticket_number})*\n"
                        f"🚚 *Vehicle:* Truck #{truck_num} ({truck_model})\n"
                        f"📌 *Fault:* {ticket.category_name} ➔ {ticket.subcategory_name}\n"
                        f"📝 *Notes:* {ticket.description}\n\n"
                        f"⏱️ *Please enter your Estimated Completion Time (e.g. 'Tomorrow 11 AM'):*"
                    )
                    return True
                elif ticket.status == "REPAIR_IN_PROGRESS":
                    msg = (
                        f"✅ Repair in progress for Ticket `{ticket.ticket_number}`.\n\n"
                        f"Tap below once wrenching is completed on the floor:"
                    )
                    buttons = [{"id": f"btn_ws_repair_done_{ticket.ticket_id}", "title": "🏁 Repair Completed"}]
                    await meta_api.send_button_message(phone, msg, buttons, header_text="WORK IN PROGRESS")
                    return True
                    
            # For Driver / Logistics Assistant / General
            await meta_api.send_text_message(
                phone,
                f"🎫 *Ticket Information:* `{ticket.ticket_number}`\n"
                f"🚚 *Vehicle:* Truck #{truck_num} ({truck_model})\n"
                f"📌 *Fault:* {ticket.category_name} ➔ {ticket.subcategory_name}\n"
                f"⏳ *Status:* `{ticket.status}`\n"
                f"⏱️ *ETA:* {ticket.expected_completion_time or 'Pending Assessment'}"
            )
            return True

    # 1.1 Test Data Management Commands (Supervisor / Admin only)
    if staff.role.upper() in {"SUPERVISOR", "LOGISTICS SUPERVISOR", "ADMIN"} and text.lower() in {"delete testing data", "delete test data", "clear test data"}:
        from manage_test_data import delete_test_data_in_session
        await delete_test_data_in_session(session)
        from app.meta_api import meta_api
        await meta_api.send_text_message(
            phone,
            "🗑️ *All Testing Data Deleted Successfully!*\n\n"
            "• Fake Truck #9999 removed\n"
            "• Test Clerk (+91 82007 13637) reset\n"
            "• Test Mechanic (+91 78599 91843) reset\n"
            "• All associated test tickets & parts requests cleared."
        )
        return True

    if staff.role.upper() in {"SUPERVISOR", "LOGISTICS SUPERVISOR", "ADMIN"} and text.lower() in {"seed testing data", "seed test data"}:
        from manage_test_data import seed_test_database_in_session
        await seed_test_database_in_session(session)
        from app.meta_api import meta_api
        await meta_api.send_text_message(
            phone,
            "✅ *Testing Data Seeded Successfully!*\n\n"
            "• Fake Truck: #9999 (Volvo FH16 - TST 9999)\n"
            "• Clerk: `+91 82007 13637`\n"
            "• Mechanic: `+91 78599 91843`\n"
            "• Supervisor: `+91 92653 68695`"
        )
        return True
        
    state = await get_user_state(session, phone)
    current_step = state.current_step if state else None
    data = state.current_data if state else {}

    # 2. Check Supervisor Handlers (Edward)
    if text.startswith("btn_ws_route_") or text.startswith("btn_ws_resolve_") or text.startswith("btn_ws_reject_") or text.startswith("btn_ws_qc_") or text.startswith("btn_ws_return_") or current_step in {"ws_reject_reason", "ws_internal_fix_notes", "ws_qc_fail_reason"}:
        handled = await handle_supervisor_action(session, staff, text, data, current_step)
        if handled:
            return True

    # 3. Check Purchasing Handlers
    if text.startswith("btn_parts_") or current_step == "ws_purchasing_inquiry":
        handled = await handle_purchasing_action(session, staff, text, data, current_step)
        if handled:
            return True

    # 4. Check Mechanic Handlers
    if text.startswith("btn_ws_parts_") or text.startswith("btn_ws_repair_done_") or text.startswith("btn_ws_skip_mech_photo") or current_step in {"ws_enter_eta", "ws_enter_part_details", "ws_parts_attach_photo", "ws_parts_clarification_reply", "ws_enter_resolution_notes", "ws_enter_costing"}:
        handled = await handle_mechanic_action(session, staff, text, image_id, data, current_step)
        if handled:
            return True

    # 5. Clerk / Panashe Flow Steps
    if current_step == "ws_truck_search":
        await handle_truck_search(session, staff, text, data)
        return True
        
    if current_step == "ws_confirm_truck":
        await handle_truck_confirmation(session, staff, text, data)
        return True
        
    if current_step == "ws_select_multi_truck":
        choice = int(text) if text.isdigit() else 1
        ids = data.get("multi_truck_ids", [])
        if 1 <= choice <= len(ids):
            data["truck_id"] = ids[choice - 1]
            await handle_truck_confirmation(session, staff, "confirm", data)
        return True
        
    if current_step == "ws_select_category":
        await handle_category_selection(session, staff, text, data)
        return True
        
    if current_step == "ws_select_subcategory":
        await handle_subcategory_selection(session, staff, text, data)
        return True
        
    if current_step == "ws_enter_description":
        await handle_description_entry(session, staff, text, image_id, data)
        return True

    if current_step == "ws_attach_clerk_photo" or text.startswith("btn_ws_skip_clerk_photo"):
        await handle_photo_step(session, staff, text, image_id, data)
        return True

    # Default fallback
    await start_workshop_flow(session, staff)
    return True
