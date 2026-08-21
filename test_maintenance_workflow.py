import asyncio
import logging
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import async_session_factory, Ticket, MaintenanceTicket, Employee, SupportAdmin, ConversationState
from app.handlers.flow_handler import handle_flow, start_ticket_creation_flow
from app.handlers.admin_handler import handle_admin_command
from app.state_manager import get_user_state

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_maint")

async def run_test():
    logger.info("Starting automated Maintenance & 2-Step Button Resolution verification test...")
    
    sender_phone = "919265368695" # Fazal Saiyed (Dual-Role: Master Admin + Maintenance Reporter)
    
    async with async_session_factory() as session:
        # Fetch employee
        e_res = await session.execute(select(Employee).where(Employee.phone == sender_phone))
        employee = e_res.scalars().first()
        
        # 1. Start Flow (Dual Role User -> Prompts 2 Buttons)
        logger.info("\n--- STEP 1: Start Flow ---")
        await start_ticket_creation_flow(session, sender_phone, employee)
        state = await get_user_state(session, sender_phone)
        logger.info(f"State after start: step='{state.current_step}'")
        assert state.current_step == "select_domain"

        # 2. Select Maintenance Domain (Tap Button [ 🛠️ Maintenance ])
        logger.info("\n--- STEP 2: Select Maintenance Domain ---")
        await handle_flow(session, employee, "btn_domain_maint", state, sender_phone=sender_phone)
        state = await get_user_state(session, sender_phone)
        logger.info(f"State after domain selection: step='{state.current_step}'")
        assert state.current_step == "select_location"

        # 3. Select Location '1' (L.G Offices)
        logger.info("\n--- STEP 3: Select Location 1 ---")
        await handle_flow(session, employee, "1", state, sender_phone=sender_phone)
        state = await get_user_state(session, sender_phone)
        logger.info(f"State after location selection: step='{state.current_step}'")
        assert state.current_step == "awaiting_room_area"

        # 4. Enter Room/Area Text
        logger.info("\n--- STEP 4: Type Room/Area ---")
        await handle_flow(session, employee, "Executive Kitchen", state, sender_phone=sender_phone)
        state = await get_user_state(session, sender_phone)
        logger.info(f"State after room entry: step='{state.current_step}'")
        assert state.current_step == "awaiting_category"

        # 5. Select Category '1' (Doors, Windows & Locks)
        logger.info("\n--- STEP 5: Select Category 1 ---")
        await handle_flow(session, employee, "1", state, sender_phone=sender_phone)
        state = await get_user_state(session, sender_phone)
        logger.info(f"State after category selection: step='{state.current_step}'")
        assert state.current_step == "awaiting_subcategory"

        # 6. Select Subcategory '1'
        logger.info("\n--- STEP 6: Select Subcategory 1 ---")
        await handle_flow(session, employee, "1", state, sender_phone=sender_phone)
        state = await get_user_state(session, sender_phone)
        logger.info(f"State after subcategory selection: step='{state.current_step}'")
        assert state.current_step == "awaiting_issue"

        # 7. Select Issue '1'
        logger.info("\n--- STEP 7: Select Issue 1 ---")
        await handle_flow(session, employee, "1", state, sender_phone=sender_phone)
        state = await get_user_state(session, sender_phone)
        logger.info(f"State after issue selection: step='{state.current_step}'")
        assert state.current_step == "awaiting_description"

        # 8. Type Issue Description
        logger.info("\n--- STEP 8: Type Issue Description ---")
        await handle_flow(session, employee, "Kitchen cabinet door latch is broken and hanging loose", state, sender_phone=sender_phone)
        state = await get_user_state(session, sender_phone)
        logger.info(f"State after description entry: step='{state.current_step}'")
        assert state.current_step == "select_priority"

        # 9. Select Priority Button [ 🔴 Critical ]
        logger.info("\n--- STEP 9: Select Priority Button ---")
        await handle_flow(session, employee, "btn_prio_crit", state, sender_phone=sender_phone)
        state = await get_user_state(session, sender_phone)
        logger.info(f"State after priority selection: step='{state.current_step}'")
        assert state.current_step == "select_safety_hazard"

        # 10. Select Safety Hazard Button [ 🟢 No - Standard Issue ]
        logger.info("\n--- STEP 10: Select Safety Hazard Button ---")
        await handle_flow(session, employee, "btn_hazard_no", state, sender_phone=sender_phone)
        state = await get_user_state(session, sender_phone)
        logger.info(f"State after safety hazard flag: step='{state.current_step}'")
        assert state.current_step == "awaiting_image"

        # 11. Tap Skip Photo Button [ ⏩ Skip Photo ] -> Ticket Created!
        logger.info("\n--- STEP 11: Skip Photo & Finalize Ticket ---")
        await handle_flow(session, employee, "btn_skip_photo", state, sender_phone=sender_phone)
        
        # Verify created ticket in DB
        t_stmt = select(MaintenanceTicket).order_by(MaintenanceTicket.ticket_id.desc())
        latest_ticket = (await session.execute(t_stmt)).scalars().first()
        logger.info(f"Created Maintenance Ticket: ID={latest_ticket.ticket_id}, Number={latest_ticket.ticket_number}, Domain={latest_ticket.domain}, Room={latest_ticket.room_area}, Priority={latest_ticket.priority_id}, Hazard={latest_ticket.is_safety_hazard}")
        assert latest_ticket.domain == "MAINTENANCE"
        assert latest_ticket.room_area == "Executive Kitchen"

        # 12. Test Admin 2-Step Resolution Workflow!
        # Admin Stanclea taps [ 🟢 Resolve Ticket ] button for latest ticket
        admin_phone = "263780099291" # Stanclea (Maintenance Support Admin)
        logger.info(f"\n--- STEP 12: Admin Stanclea taps [ 🟢 Resolve Ticket ] button for {latest_ticket.ticket_number} ---")
        resolved_cmd = f"resolve {latest_ticket.ticket_number}"
        is_handled = await handle_admin_command(session, admin_phone, resolved_cmd)
        logger.info(f"Admin command handled: {is_handled}")

        admin_state = await get_user_state(session, admin_phone)
        logger.info(f"Admin State after button tap: flow='{admin_state.flow_name}', step='{admin_state.current_step}'")
        assert admin_state.current_step == "awaiting_admin_resolution_note"

        # 13. Admin types resolution note text
        logger.info("\n--- STEP 13: Admin types resolution note ---")
        note_text = "Replaced cabinet hinge screws, aligned door, and tested latch mechanism."
        await handle_admin_command(session, admin_phone, note_text)

        # Check final ticket state
        await session.refresh(latest_ticket)
        logger.info(f"Ticket after resolution: Status={latest_ticket.status_id}, Resolution Note='{latest_ticket.resolution_note}'")
        assert latest_ticket.status_id == 3 # Resolved
        assert latest_ticket.resolution_note == note_text

        logger.info("\n🎉 ALL VERIFICATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(run_test())
