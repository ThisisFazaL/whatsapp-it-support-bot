import asyncio
import datetime
import logging
from typing import Dict, Any, List
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select

from app.database import (
    Base, Employee, SupportAdmin, Category, Subcategory, IssueType,
    Priority, TicketStatus, Location, Ticket, MaintenanceTicket,
    ConversationState
)
from app.state_manager import get_user_state, set_user_state, clear_user_state
from app.handlers.flow_handler import handle_flow, start_ticket_creation_flow
from app.handlers.admin_handler import handle_admin_command
from app.handlers.resolution_handler import handle_resolution_confirmation
from app.handlers.my_tickets_handler import handle_my_tickets
from app.workshop.models import (
    WorkshopTruck, WorkshopStaff, WorkshopCategory, WorkshopSubcategory,
    WorkshopTicket, WorkshopPartsRequest
)
from app.workshop.router import handle_workshop_message
from app.config import settings
from app.meta_api import meta_api

logger = logging.getLogger("auditor")

LAST_AUDIT_RESULT: Dict[str, Any] = {
    "timestamp": None,
    "total_tests": 0,
    "passed": 0,
    "failed": 0,
    "status": "NOT_RUN_YET",
    "failures": []
}

async def setup_test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return session_factory

async def seed_master_data(session: AsyncSession):
    # Priorities & Status
    session.add_all([
        Priority(priority_id=1, priority_name="Low"),
        Priority(priority_id=2, priority_name="Medium"),
        Priority(priority_id=3, priority_name="Critical"),
        TicketStatus(status_id=1, status_name="Open"),
        TicketStatus(status_id=2, status_name="In Progress"),
        TicketStatus(status_id=3, status_name="Resolved"),
        TicketStatus(status_id=4, status_name="Closed"),
    ])
    # Locations
    austin = Location(location_name="6 Austin Road Workington")
    coventry = Location(location_name="110 Coventry Road Workington")
    session.add_all([austin, coventry])
    await session.flush()

    # Categories
    it_cat = Category(category_name="IT & Computing Equipment", domain="IT", active=True)
    maint_cat = Category(category_name="Plumbing & Water Systems", domain="MAINTENANCE", active=True)
    session.add_all([it_cat, maint_cat])
    await session.flush()

    it_sub = Subcategory(category_id=it_cat.category_id, subcategory_name="Laptops & Desktops", active=True)
    maint_sub = Subcategory(category_id=maint_cat.category_id, subcategory_name="Pipes & Taps", active=True)
    session.add_all([it_sub, maint_sub])
    await session.flush()

    it_issue = IssueType(subcategory_id=it_sub.subcategory_id, issue_name="Will not power on", active=True)
    maint_issue = IssueType(subcategory_id=maint_sub.subcategory_id, issue_name="Tap leaking", active=True)
    session.add_all([it_issue, maint_issue])

    # Employees & Admins
    emp_regular = Employee(employee_code="EMP_001", full_name="Regular Staff", phone="263771111111", location_id=austin.location_id, active=True)
    emp_dual = Employee(employee_code="EMP_002", full_name="Dual Reporter", phone="263772222222", location_id=coventry.location_id, is_maintenance_reporter=True, active=True)
    
    admin_it = SupportAdmin(full_name="Kevin Support", phone="263718627526", is_maintenance_admin=False, is_master_admin=False, active=True)
    admin_maint = SupportAdmin(full_name="Stanclea Projects", phone="263780099291", is_maintenance_admin=True, is_master_admin=False, active=True)
    admin_master = SupportAdmin(full_name="Fazal Master", phone="919265368695", is_maintenance_admin=False, is_master_admin=True, active=True)
    session.add_all([emp_regular, emp_dual, admin_it, admin_maint, admin_master])
    
    # Workshop Staff & Truck
    ws_truck = WorkshopTruck(truck_number="1045", plate_number="ABZ 1045", model_make="Volvo FH16", body_type="Horse", active=True)
    ws_clerk = WorkshopStaff(full_name="Panashe Clerk", phone="263773333333", role="CLERK", active=True)
    ws_super = WorkshopStaff(full_name="Edward Supervisor", phone="263774444444", role="SUPERVISOR", active=True)
    ws_mech = WorkshopStaff(full_name="John Mechanic", phone="263775555555", role="MECHANIC", active=True)
    ws_buyer = WorkshopStaff(full_name="Sarah Purchasing", phone="263776666666", role="PURCHASING", active=True)
    session.add_all([ws_truck, ws_clerk, ws_super, ws_mech, ws_buyer])

    await session.commit()

async def run_daily_button_audit() -> Dict[str, Any]:
    """
    Executes an isolated, automated synthetic audit across all 25+ WhatsApp interactive
    buttons, workflows, and state machines without sending real messages or modifying live data.
    """
    global LAST_AUDIT_RESULT
    audit_time = datetime.datetime.utcnow().isoformat()
    test_results: List[Dict[str, Any]] = []

    def record_test(category: str, test_name: str, passed: bool, details: str = ""):
        status = "PASS" if passed else "FAIL"
        test_results.append({
            "group": category,
            "test": test_name,
            "status": status,
            "details": details
        })

    session_factory = await setup_test_db()
    
    try:
        # Mock Meta API so no real WhatsApp calls are made during the audit
        with patch("app.meta_api.meta_api.send_text_message", new_callable=AsyncMock), \
             patch("app.meta_api.meta_api.send_button_message", new_callable=AsyncMock), \
             patch("app.meta_api.meta_api.send_image_message", new_callable=AsyncMock):

            async with session_factory() as session:
                await seed_master_data(session)

                # -----------------------------------------------------------------
                # TEST GROUP 1: Dual-Role Domain Selection Buttons
                # -----------------------------------------------------------------
                emp_dual = (await session.execute(select(Employee).where(Employee.phone == "263772222222"))).scalars().first()
                
                # 1.1 Start Flow for Dual Reporter -> Expects 2 buttons (IT vs Projects)
                await start_ticket_creation_flow(session, "263772222222", emp_dual)
                state = await get_user_state(session, "263772222222")
                record_test("Domain Selection", "start_ticket_creation_flow (Dual Role)", state.current_step == "select_domain", f"Step is {state.current_step if state else None}")

                # 1.2 Tap btn_domain_it
                await handle_flow(session, emp_dual, "btn_domain_it", state)
                state_it = await get_user_state(session, "263772222222")
                record_test("Domain Selection", "Button: btn_domain_it -> Skip location, prompt categories", state_it.current_step == "awaiting_category" and state_it.current_data.get("domain") == "IT", f"Step={state_it.current_step}, domain={state_it.current_data.get('domain')}")

                # 1.3 Reset & Tap btn_domain_maint
                await set_user_state(session, "263772222222", "select_domain", {})
                state_reset = await get_user_state(session, "263772222222")
                await handle_flow(session, emp_dual, "btn_domain_maint", state_reset)
                state_maint = await get_user_state(session, "263772222222")
                record_test("Domain Selection", "Button: btn_domain_maint -> Select Location prompt", state_maint.current_step == "select_location" and state_maint.current_data.get("domain") == "MAINTENANCE", f"Step={state_maint.current_step}, domain={state_maint.current_data.get('domain')}")

                # -----------------------------------------------------------------
                # TEST GROUP 2: Priority Selection Buttons
                # -----------------------------------------------------------------
                emp_reg = (await session.execute(select(Employee).where(Employee.phone == "263771111111"))).scalars().first()
                for p_btn, p_val in [("btn_prio_low", 1), ("btn_prio_med", 2), ("btn_prio_crit", 3)]:
                    await set_user_state(session, "263771111111", "select_priority", {"domain": "IT", "description": "Keyboard issue"})
                    s = await get_user_state(session, "263771111111")
                    await handle_flow(session, emp_reg, p_btn, s)
                    s_after = await get_user_state(session, "263771111111")
                    record_test("Priority Buttons", f"Button: {p_btn}", s_after.current_step == "awaiting_image" and s_after.current_data.get("priority_id") == p_val, f"Priority ID: {s_after.current_data.get('priority_id')}")

                # -----------------------------------------------------------------
                # TEST GROUP 3: Maintenance Safety Hazard Check Buttons
                # -----------------------------------------------------------------
                await set_user_state(session, "263772222222", "select_priority", {"domain": "MAINTENANCE", "description": "Water leak"})
                s = await get_user_state(session, "263772222222")
                await handle_flow(session, emp_dual, "btn_prio_crit", s)
                s_after = await get_user_state(session, "263772222222")
                record_test("Safety Hazard", "Maintenance priority leads to select_safety_hazard", s_after.current_step == "select_safety_hazard", f"Step: {s_after.current_step}")

                # 3.1 btn_hazard_yes
                await handle_flow(session, emp_dual, "btn_hazard_yes", s_after)
                s_haz_yes = await get_user_state(session, "263772222222")
                record_test("Safety Hazard", "Button: btn_hazard_yes", s_haz_yes.current_step == "awaiting_image" and s_haz_yes.current_data.get("is_safety_hazard") is True, f"Hazard: {s_haz_yes.current_data.get('is_safety_hazard')}")

                # 3.2 btn_hazard_no
                await set_user_state(session, "263772222222", "select_safety_hazard", {"domain": "MAINTENANCE", "description": "Water leak"})
                s_haz = await get_user_state(session, "263772222222")
                await handle_flow(session, emp_dual, "btn_hazard_no", s_haz)
                s_haz_no = await get_user_state(session, "263772222222")
                record_test("Safety Hazard", "Button: btn_hazard_no", s_haz_no.current_step == "awaiting_image" and s_haz_no.current_data.get("is_safety_hazard") is False, f"Hazard: {s_haz_no.current_data.get('is_safety_hazard')}")

                # -----------------------------------------------------------------
                # TEST GROUP 4: Skip Photo Button & Final Ticket Generation
                # -----------------------------------------------------------------
                await set_user_state(session, "263771111111", "awaiting_image", {
                    "domain": "IT",
                    "category_id": 1,
                    "subcategory_id": 1,
                    "issue_type_id": 1,
                    "description": "Laptop battery swollen",
                    "priority_id": 3
                })
                s_img = await get_user_state(session, "263771111111")
                await handle_flow(session, emp_reg, "btn_skip_photo", s_img)
                
                stmt_t = select(Ticket).where(Ticket.description == "Laptop battery swollen")
                tkt = (await session.execute(stmt_t)).scalars().first()
                s_final = await get_user_state(session, "263771111111")
                record_test("Skip Photo & Creation", "Button: btn_skip_photo -> Creates Ticket & Clears State", tkt is not None and s_final is None, f"Created Ticket: {tkt.ticket_number if tkt else 'None'}, State Cleared: {s_final is None}")

                # -----------------------------------------------------------------
                # TEST GROUP 5: Support Admin Interactive Buttons
                # -----------------------------------------------------------------
                # 5.1 cmd_my_assigned_tickets
                handled_my_assigned = await handle_admin_command(session, "263718627526", "cmd_my_assigned_tickets")
                record_test("Admin Buttons", "Button: cmd_my_assigned_tickets", handled_my_assigned is True)

                # 5.2 cmd_unassigned_tickets
                handled_unassigned = await handle_admin_command(session, "263718627526", "cmd_unassigned_tickets")
                record_test("Admin Buttons", "Button: cmd_unassigned_tickets", handled_unassigned is True)

                # 5.3 cmd_raise_ticket
                handled_raise = await handle_admin_command(session, "263718627526", "cmd_raise_ticket")
                record_test("Admin Buttons", "Button: cmd_raise_ticket", handled_raise is True)

                # 5.4 claim_{ticket_number}
                if tkt:
                    handled_claim = await handle_admin_command(session, "263718627526", f"claim_{tkt.ticket_number}")
                    await session.refresh(tkt)
                    record_test("Admin Buttons", f"Button: claim_{tkt.ticket_number} -> Sets In Progress", handled_claim is True and tkt.status_id == 2, f"Status ID: {tkt.status_id}")

                # 5.5 resolve_{ticket_number}
                if tkt:
                    handled_resolve_btn = await handle_admin_command(session, "263718627526", f"resolve_{tkt.ticket_number}")
                    s_admin = await get_user_state(session, "263718627526")
                    record_test("Admin Buttons", f"Button: resolve_{tkt.ticket_number} -> Prompts for note", handled_resolve_btn is True and s_admin.current_step == "awaiting_admin_resolution_note", f"Step: {s_admin.current_step if s_admin else None}")

                    # Submit note
                    handled_note = await handle_admin_command(session, "263718627526", "Replaced with new OEM battery and tested health")
                    await session.refresh(tkt)
                    record_test("Admin Resolution", "Admin types resolution note -> Sets status to Resolved (3)", handled_note is True and tkt.status_id == 3 and tkt.resolution_note == "Replaced with new OEM battery and tested health", f"Status: {tkt.status_id}, Note: {tkt.resolution_note}")

                # -----------------------------------------------------------------
                # TEST GROUP 6: Reporter Confirmation Loop Buttons
                # -----------------------------------------------------------------
                if tkt:
                    # 6.1 Confirm and Close button: confirm_resolve_{ticket_number}
                    await handle_resolution_confirmation(session, "263771111111", f"confirm_resolve_{tkt.ticket_number}", {"ticket_id": tkt.ticket_id, "ticket_number": tkt.ticket_number, "is_maint": False})
                    await session.refresh(tkt)
                    record_test("Reporter Confirmation", f"Button: confirm_resolve_{tkt.ticket_number} -> Marks Closed (4)", tkt.status_id == 4, f"Status ID: {tkt.status_id}")

                    # 6.2 Reopen button: reopen_{ticket_number}
                    await handle_resolution_confirmation(session, "263771111111", f"reopen_{tkt.ticket_number}", {"ticket_id": tkt.ticket_id, "ticket_number": tkt.ticket_number, "is_maint": False})
                    await session.refresh(tkt)
                    s_reopen = await get_user_state(session, "263771111111")
                    record_test("Reporter Confirmation", f"Button: reopen_{tkt.ticket_number} -> Reopens Ticket to Open (1)", tkt.status_id == 1 and s_reopen is None, f"Status: {tkt.status_id}")

                # -----------------------------------------------------------------
                # TEST GROUP 7: Workshop Subsystem Buttons
                # -----------------------------------------------------------------
                ws_super = (await session.execute(select(WorkshopStaff).where(WorkshopStaff.phone == "263774444444"))).scalars().first()
                ws_buyer = (await session.execute(select(WorkshopStaff).where(WorkshopStaff.phone == "263776666666"))).scalars().first()
                ws_mech = (await session.execute(select(WorkshopStaff).where(WorkshopStaff.phone == "263775555555"))).scalars().first()

                ws_tkt = WorkshopTicket(
                    ticket_number="TKT-FLT-20260904-00001",
                    truck_id=1,
                    description="Brake booster leaking air",
                    status="UNDER_REVIEW"
                )
                session.add(ws_tkt)
                await session.commit()
                await session.refresh(ws_tkt)

                # 7.1 Supervisor Route to Workshop Button: btn_ws_route_work_{ticket_id}
                h_ws_route = await handle_workshop_message(session, ws_super, f"btn_ws_route_work_{ws_tkt.ticket_id}")
                await session.refresh(ws_tkt)
                record_test("Workshop Buttons", "Supervisor Button: btn_ws_route_work_ -> WITH_MECHANIC", h_ws_route is True and ws_tkt.status == "WITH_MECHANIC", f"Status: {ws_tkt.status}")

                # 7.2 Supervisor Resolve Internally Button: btn_ws_resolve_intern_{ticket_id}
                h_ws_res = await handle_workshop_message(session, ws_super, f"btn_ws_resolve_intern_{ws_tkt.ticket_id}")
                s_ws_res = await get_user_state(session, ws_super.phone)
                record_test("Workshop Buttons", "Supervisor Button: btn_ws_resolve_intern_ -> Prompts internal notes", h_ws_res is True and s_ws_res.current_step == "ws_internal_fix_notes", f"Step: {s_ws_res.current_step if s_ws_res else None}")

                # 7.3 Supervisor Reject Button: btn_ws_reject_{ticket_id}
                h_ws_rej = await handle_workshop_message(session, ws_super, f"btn_ws_reject_{ws_tkt.ticket_id}")
                s_ws_rej = await get_user_state(session, ws_super.phone)
                record_test("Workshop Buttons", "Supervisor Button: btn_ws_reject_ -> Prompts reject reason", h_ws_rej is True and s_ws_rej.current_step == "ws_reject_reason", f"Step: {s_ws_rej.current_step if s_ws_rej else None}")

                # 7.4 Mechanic Request Parts Button: btn_ws_parts_req_{ticket_id}
                h_mech_parts = await handle_workshop_message(session, ws_mech, f"btn_ws_parts_req_{ws_tkt.ticket_id}")
                s_ws_mech = await get_user_state(session, ws_mech.phone)
                record_test("Workshop Buttons", "Mechanic Button: btn_ws_parts_req_ -> Prompts part details", h_mech_parts is True and s_ws_mech.current_step == "ws_enter_part_details", f"Step: {s_ws_mech.current_step if s_ws_mech else None}")

                # 7.5 Mechanic Repair Completed Button: btn_ws_repair_done_{ticket_id}
                await clear_user_state(session, ws_mech.phone)
                h_mech_done = await handle_workshop_message(session, ws_mech, f"btn_ws_repair_done_{ws_tkt.ticket_id}")
                s_ws_done = await get_user_state(session, ws_mech.phone)
                record_test("Workshop Buttons", "Mechanic Button: btn_ws_repair_done_ -> Prompts resolution notes", h_mech_done is True and s_ws_done.current_step == "ws_enter_resolution_notes", f"Step: {s_ws_done.current_step if s_ws_done else None}")

                # 7.6 Purchasing Parts Clarification Button: btn_parts_need_info_{request_id}
                part_req = WorkshopPartsRequest(ticket_id=ws_tkt.ticket_id, part_name="Air Booster Valve", status="PENDING")
                session.add(part_req)
                await session.commit()
                await session.refresh(part_req)

                h_buyer_clarify = await handle_workshop_message(session, ws_buyer, f"btn_parts_need_info_{part_req.request_id}")
                s_ws_buyer = await get_user_state(session, ws_buyer.phone)
                record_test("Workshop Buttons", "Purchasing Button: btn_parts_need_info_ -> Prompts inquiry question", h_buyer_clarify is True and s_ws_buyer.current_step == "ws_purchasing_inquiry", f"Step: {s_ws_buyer.current_step if s_ws_buyer else None}")

                # 7.7 Purchasing Mark Received Button: btn_parts_received_{request_id}
                h_buyer_recv = await handle_workshop_message(session, ws_buyer, f"btn_parts_received_{part_req.request_id}")
                await session.refresh(part_req)
                record_test("Workshop Buttons", "Purchasing Button: btn_parts_received_ -> Sets status to RECEIVED", h_buyer_recv is True and part_req.status == "RECEIVED", f"Status: {part_req.status}")

    except Exception as e:
        logger.error(f"Error during button audit execution: {e}", exc_info=True)
        record_test("System Error", "Audit Runner", False, str(e))

    passed_count = sum(1 for r in test_results if r["status"] == "PASS")
    failed_count = sum(1 for r in test_results if r["status"] == "FAIL")
    failures = [r for r in test_results if r["status"] == "FAIL"]

    LAST_AUDIT_RESULT = {
        "timestamp": audit_time,
        "total_tests": len(test_results),
        "passed": passed_count,
        "failed": failed_count,
        "status": "HEALTHY" if failed_count == 0 else "DEGRADED",
        "failures": failures,
        "details": test_results
    }

    return LAST_AUDIT_RESULT

async def execute_and_alert_daily_audit():
    """
    Runs the audit and sends an immediate alert to Master Admin if any workflow fails.
    """
    logger.info("Executing scheduled Daily Bot Workflow & Button Audit...")
    result = await run_daily_button_audit()
    
    if result["failed"] > 0:
        logger.warning(f"Daily Audit FAILED with {result['failed']} error(s)!")
        master_phone = settings.master_admin_phone or "919265368695"
        fail_summary = "\n".join([f"• [{f['group']}] {f['test']}: {f.get('details', '')}" for f in result["failures"][:5]])
        alert_msg = (
            f"🚨 *[SYSTEM ALERT] DAILY BOT AUDIT FAILED*\n\n"
            f"⚠️ *Failed Tests:* {result['failed']} / {result['total_tests']}\n"
            f"🕒 *Timestamp:* {result['timestamp']}\n\n"
            f"*Failure Details:*\n{fail_summary}\n\n"
            f"Please inspect logs immediately."
        )
        try:
            await meta_api.send_text_message(master_phone, alert_msg)
        except Exception as e:
            logger.error(f"Failed to deliver audit alert to Master Admin: {e}")
    else:
        logger.info(f"Daily Audit PASSED successfully! ({result['passed']}/{result['total_tests']} workflows 100% operational).")


