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
