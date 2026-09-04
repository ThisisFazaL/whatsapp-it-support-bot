import asyncio
import os
import sys

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings
from app.database import Base
from app.workshop.models import (
    WorkshopTruck, WorkshopStaff, WorkshopCategory, WorkshopSubcategory,
    WorkshopTicket, WorkshopPartsRequest
)
from app.workshop.router import handle_workshop_message, get_workshop_staff

# Mock meta_api to capture outgoing WhatsApp messages during tests
from app.meta_api import meta_api

captured_messages = []

async def mock_send_text(to_phone: str, text: str, **kwargs):
    captured_messages.append({"type": "text", "to": to_phone, "text": text, "kwargs": kwargs})
    print(f"\n[WhatsApp to +{to_phone}]:\n{text}\n" + "-"*50)

async def mock_send_button(to_phone: str, body_text: str, buttons: list, header_text: str = None, **kwargs):
    btn_titles = [b.get("title") for b in buttons]
    btn_ids = [b.get("id") for b in buttons]
    captured_messages.append({"type": "button", "to": to_phone, "text": body_text, "buttons": buttons, "kwargs": kwargs})
    print(f"\n[WhatsApp Buttons to +{to_phone}]:\n[{header_text or 'MENU'}]\n{body_text}\nButtons: {btn_titles} (IDs: {btn_ids})\n" + "-"*50)

async def mock_send_image(to_phone: str, image_id: str, caption: str = ""):
    captured_messages.append({"type": "image", "to": to_phone, "image_id": image_id, "caption": caption})
    print(f"\n[WhatsApp PHOTO ATTACHMENT to +{to_phone}]:\nImage ID: {image_id}\nCaption: {caption}\n" + "-"*50)

meta_api.send_text_message = mock_send_text
meta_api.send_button_message = mock_send_button
meta_api.send_image_message = mock_send_image

async def run_test():
    print("="*60)
    print("TEST: STARTING COMPLETE WORKSHOP WORKFLOW SIMULATION TEST")
    print("="*60)

    # Use SQLite for testing
    db_url = "sqlite+aiosqlite:///./itsupport.db"
    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # Guarantee real fleet and test staff exist in test session
        from seed_workshop_data import seed_workshop_data_in_session
        await seed_workshop_data_in_session(session)

        # Seed test staff if missing
        test_staff_list = [
            {"full_name": "Tinashe Moyo (Driver)", "phone": "919876543220", "role": "DRIVER"},
            {"full_name": "Edward Marufu (Supervisor)", "phone": "919876543221", "role": "SUPERVISOR"},
            {"full_name": "Blessing Moyo (Mechanic)", "phone": "919876543222", "role": "MECHANIC"},
            {"full_name": "Purchasing Team", "phone": "919876543224", "role": "PURCHASING"},
        ]
        for s in test_staff_list:
            stmt = select(WorkshopStaff).where(WorkshopStaff.phone == s["phone"])
            existing = (await session.execute(stmt)).scalars().first()
            if not existing:
                session.add(WorkshopStaff(**s, active=True))
        await session.commit()

        # Load Staff
        driver = await get_workshop_staff(session, "919876543220") # Driver
        edward = await get_workshop_staff(session, "919876543221")  # Supervisor
        blessing = await get_workshop_staff(session, "919876543222") # Mechanic
        purchasing = await get_workshop_staff(session, "919876543224") # Purchasing

        assert driver is not None, "Driver not found in DB"
        assert edward is not None, "Edward not found in DB"
        assert blessing is not None, "Blessing not found in DB"
        assert purchasing is not None, "Purchasing not found in DB"

        print(f"[OK] Staff loaded: Driver ({driver.role}), Edward ({edward.role}), Blessing ({blessing.role}), Purchasing ({purchasing.role})")

        # -------------------------------------------------------------
        # STAGE 1: Driver Logs Issue for Real Truck AGZ 7331 (7331)
        # -------------------------------------------------------------
        print("\n[STAGE 1] Driver Logs Issue for Real Truck #7331 (AGZ 7331)...")
        
        # 1.1 Driver sends "Hi"
        await handle_workshop_message(session, driver, "Hi")
        
        # 1.2 Driver types "7331" (or "AGZ7331")
        await handle_workshop_message(session, driver, "7331")
        
        # 1.3 Driver confirms truck
        await handle_workshop_message(session, driver, "btn_ws_confirm_truck")
        
        # 1.4 Driver selects Category 1 (Brakes & Air Pressure)
        await handle_workshop_message(session, driver, "1")
        
        # 1.5 Driver selects Subcategory 1 (Air Pressure Leak)
        await handle_workshop_message(session, driver, "1")
        
        # 1.6 Driver inputs description (Step 1)
        await handle_workshop_message(session, driver, "Air pressure drops rapidly when footbrake pressed")
        
        # 1.7 Driver sends optional photo (Step 2)
        await handle_workshop_message(session, driver, "Photo of leaking line", image_id="img_leak_001")

        # Verify Ticket Created
        stmt = select(WorkshopTicket).order_by(WorkshopTicket.ticket_id.desc())
        ticket = (await session.execute(stmt)).scalars().first()
        assert ticket is not None, "Ticket was not created"
        assert ticket.status == "UNDER_REVIEW", f"Expected UNDER_REVIEW, got {ticket.status}"
        assert ticket.image_id == "img_leak_001", "Image attachment missing"
        print(f"[PASS] STAGE 1: Ticket {ticket.ticket_number} created with status '{ticket.status}' for IVECO STRALIS 330 (AGZ 7331)!")

        # -------------------------------------------------------------
        # STAGE 2: Edward Gatekeeper Review -> Send to Workshop
        # -------------------------------------------------------------
        print(f"\n[STAGE 2] Edward Reviews Ticket {ticket.ticket_number}...")
        
        # Edward taps "Send to Workshop"
        await handle_workshop_message(session, edward, f"btn_ws_route_work_{ticket.ticket_id}")
        
        await session.refresh(ticket)
        assert ticket.status == "WITH_MECHANIC", f"Expected WITH_MECHANIC, got {ticket.status}"
        assert ticket.assigned_mechanic_id is not None, "Mechanic not assigned"
        assigned_mechanic = await session.get(WorkshopStaff, ticket.assigned_mechanic_id)
        print(f"[PASS] STAGE 2: Ticket routed to Workshop Floor. Assigned to {assigned_mechanic.full_name}!")

        # -------------------------------------------------------------
        # STAGE 3: Mechanic Sets ETA & Requests Parts
        # -------------------------------------------------------------
        print(f"\n[STAGE 3] Mechanic {assigned_mechanic.full_name} Sets ETA & Requests Parts...")
        
        # 3.1 Mechanic enters ETA
        await handle_workshop_message(session, assigned_mechanic, "Tomorrow 11 AM")
        await session.refresh(ticket)
        assert ticket.expected_completion_time == "Tomorrow 11 AM", "ETA not saved"

        # 3.2 Mechanic taps "Request Parts"
        await handle_workshop_message(session, assigned_mechanic, f"btn_ws_parts_req_{ticket.ticket_id}")

        # 3.3 Mechanic enters part name (Step 1)
        await handle_workshop_message(session, assigned_mechanic, "1x Wabco 4-way protection valve")
        
        # 3.4 Mechanic attaches sample photo (Step 2)
        await handle_workshop_message(session, assigned_mechanic, "Sample valve image", image_id="img_valve_sample_01")
        
        await session.refresh(ticket)
        assert ticket.status == "AWAITING_PARTS", f"Expected AWAITING_PARTS, got {ticket.status}"
        
        stmt_req = select(WorkshopPartsRequest).where(WorkshopPartsRequest.ticket_id == ticket.ticket_id)
        parts_req = (await session.execute(stmt_req)).scalars().first()
        assert parts_req is not None, "Parts request not created"
        assert parts_req.sample_image_id == "img_valve_sample_01"
        print(f"[PASS] STAGE 3: Parts requested: '{parts_req.part_name}'. Status: '{ticket.status}'!")

        # -------------------------------------------------------------
        # STAGE 4: Purchasing Clarification Loop (Need Info / Sample)
        # -------------------------------------------------------------
        print("\n[STAGE 4] Purchasing Requests Clarification & Receives Parts...")
        
        # 4.1 Purchasing taps "Need Info / Sample"
        await handle_workshop_message(session, purchasing, f"btn_parts_need_info_{parts_req.request_id}")

        # 4.2 Purchasing enters inquiry note
        await handle_workshop_message(session, purchasing, "Please provide OEM part number stamped on data plate or bring sample.")
        await session.refresh(parts_req)
        await session.refresh(ticket)
        assert parts_req.status == "INFO_REQUESTED", f"Expected INFO_REQUESTED, got {parts_req.status}"
        assert ticket.status == "INFO_REQUESTED", f"Expected INFO_REQUESTED, got {ticket.status}"
        print(f"[PASS] STAGE 4.1: Clarification inquiry recorded: '{parts_req.clarification_note}'!")

        # 4.3 Mechanic replies on WhatsApp with OEM # and close-up photo
        await handle_workshop_message(session, assigned_mechanic, "OEM Part # is 434 200 001 0", image_id="img_valve_oem_tag")
        await session.refresh(parts_req)
        assert parts_req.clarification_response == "OEM Part # is 434 200 001 0"
        assert parts_req.clarification_image_id == "img_valve_oem_tag"
        print("[PASS] STAGE 4.2: Mechanic replied with OEM serial number and photo!")

        # 4.4 Purchasing receives spares and taps "Part Received"
        await handle_workshop_message(session, purchasing, f"btn_parts_received_{parts_req.request_id}")
        await session.refresh(parts_req)
        await session.refresh(ticket)
        assert parts_req.status == "RECEIVED"
        assert parts_req.received_at is not None
        assert ticket.status == "REPAIR_IN_PROGRESS", f"Expected REPAIR_IN_PROGRESS, got {ticket.status}"
        print(f"[PASS] STAGE 4.3: Part received. Ticket status: '{ticket.status}'!")

        # -------------------------------------------------------------
        # STAGE 5: Mechanic Completes Repair, Adds Notes & Costing
        # -------------------------------------------------------------
        print("\n[STAGE 5] Mechanic Completes Repair, Resolution Notes & Costing...")
        
        # 5.1 Mechanic taps "Repair Completed"
        await handle_workshop_message(session, assigned_mechanic, f"btn_ws_repair_done_{ticket.ticket_id}")
        
        # 5.2 Mechanic enters Resolution Notes
        await handle_workshop_message(session, assigned_mechanic, "Replaced faulty Wabco 4-way valve, flushed lines and tightened unions.")
        
        # 5.3 Mechanic enters Costing
        await handle_workshop_message(session, assigned_mechanic, "Parts: $140, Labour: $30, Total: $170")
        
        await session.refresh(ticket)
        assert ticket.status == "AWAITING_TEST", f"Expected AWAITING_TEST, got {ticket.status}"
        assert ticket.cost_total == "Parts: $140, Labour: $30, Total: $170"
        assert ticket.sla_result == "ON_TIME"
        print(f"[PASS] STAGE 5: Repair completed! Notes: '{ticket.resolution_notes}', Cost: '{ticket.cost_total}'. Status: '{ticket.status}'!")

        # -------------------------------------------------------------
        # STAGE 6: Supervisor QC Testing & Rework Loop
        # -------------------------------------------------------------
        print("\n[STAGE 6] Edward Conducts QC Road-Test & Rework Loop...")
        
        # 6.1 Edward Fails First Test -> Rework
        await handle_workshop_message(session, edward, f"btn_ws_qc_fail_{ticket.ticket_id}")
        await handle_workshop_message(session, edward, "Air leak still audible when auxiliary compressor cuts out.")
        
        await session.refresh(ticket)
        assert ticket.status == "REWORK_REQUIRED", f"Expected REWORK_REQUIRED, got {ticket.status}"
        assert ticket.qc_passed == False
        assert ticket.qc_failure_reason == "Air leak still audible when auxiliary compressor cuts out."
        print(f"[PASS] STAGE 6.1: Rework triggered cleanly! Reason: '{ticket.qc_failure_reason}'. Status: '{ticket.status}'!")

        # 6.2 Mechanic re-fixes on floor and taps "Repair Completed" again
        await handle_workshop_message(session, assigned_mechanic, f"btn_ws_repair_done_{ticket.ticket_id}")
        await handle_workshop_message(session, assigned_mechanic, "Replaced auxiliary line seal and re-torqued union.")
        await handle_workshop_message(session, assigned_mechanic, "Total: $170 (No extra cost)")

        # 6.3 Edward Passes Second QC Test
        await handle_workshop_message(session, edward, f"btn_ws_qc_pass_{ticket.ticket_id}")
        
        # 6.4 Edward Confirms Return to Fleet
        await handle_workshop_message(session, edward, f"btn_ws_return_fleet_{ticket.ticket_id}")
        
        await session.refresh(ticket)
        assert ticket.status == "CLOSED", f"Expected CLOSED, got {ticket.status}"
        assert ticket.qc_passed == True
        assert ticket.return_to_fleet_at is not None
        print(f"[PASS] STAGE 6.2: Vehicle passed QC and returned to active fleet! Final Status: '{ticket.status}'!")

    print("="*60)
    print("ALL WORKSHOP WORKFLOW SIMULATION TESTS PASSED 100% PERFECTLY WITH REAL FLEET DATA!")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(run_test())
