import datetime
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.meta_api import meta_api
from app.state_manager import set_user_state, clear_user_state
from app.workshop.models import WorkshopStaff, WorkshopTicket, WorkshopPartsRequest

async def get_ticket_with_truck(session: AsyncSession, ticket_id: int) -> WorkshopTicket:
    stmt = select(WorkshopTicket).options(selectinload(WorkshopTicket.truck)).where(WorkshopTicket.ticket_id == ticket_id)
    return (await session.execute(stmt)).scalars().first()

async def finalize_parts_request(session: AsyncSession, staff: WorkshopStaff, data: dict):
    phone = staff.phone
    ticket_id = data.get("ticket_id")
    ticket = await get_ticket_with_truck(session, ticket_id)
    part_name = data.get("part_name", "Spare Part")
    part_description = data.get("part_description", part_name)
    sample_image_id = data.get("sample_image_id")
    
    if ticket:
        parts_req = WorkshopPartsRequest(
            ticket_id=ticket.ticket_id,
            part_name=part_name,
            part_description=part_description,
            sample_image_id=sample_image_id,
            status="PENDING"
        )
        session.add(parts_req)
        ticket.status = "AWAITING_PARTS"
        await session.commit()
        await session.refresh(parts_req)
        await clear_user_state(session, phone)
        
        await meta_api.send_text_message(
            phone,
            f"✅ Parts request for '*{part_name}*' sent to Purchasing Team.\n⏳ Status: *AWAITING PARTS*."
        )
        if ticket.logged_by_staff_id:
            raiser = await session.get(WorkshopStaff, ticket.logged_by_staff_id)
            if raiser:
                truck_num = ticket.truck.truck_number if ticket.truck else ""
                await meta_api.send_text_message(
                    raiser.phone,
                    f"📦 *Parts Requested for Truck #{truck_num}*\n"
                    f"🎫 Ticket: `{ticket.ticket_number}`\n"
                    f"Part: *{part_name}*\n"
                    f"⏳ Status: Awaiting delivery from Purchasing Team."
                )
        
        stmt = select(WorkshopStaff).where(WorkshopStaff.role == "PURCHASING", WorkshopStaff.active == True)
        purchasing_team = (await session.execute(stmt)).scalars().all()
        truck_num = ticket.truck.truck_number if ticket.truck else ""
        truck_model = ticket.truck.model_make if ticket.truck else ""
        
        for p in purchasing_team:
            p_msg = (
                f"🛒 *NEW PARTS REQUISITION*\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎫 *Ticket ID:* `{ticket.ticket_number}`\n"
                f"🚚 *Vehicle:* Truck #{truck_num} ({truck_model})\n"
                f"👨‍🔧 *Mechanic:* {staff.full_name}\n"
                f"📦 *Part Required:* {part_name}\n"
                f"🖼️ *Sample Photo:* {'Attached' if sample_image_id else 'None'}\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"Please confirm action:"
            )
            buttons = [
                {"id": f"btn_parts_received_{parts_req.request_id}", "title": "📦 Part Received"},
                {"id": f"btn_parts_need_info_{parts_req.request_id}", "title": "❓ Need Info/Sample"}
            ]
            await meta_api.send_button_message(
                p.phone,
                p_msg,
                buttons,
                header_text="PARTS REQUEST",
                fallback_template="workshop_parts_alert",
                template_params=[ticket.ticket_number, f"Truck #{truck_num} ({truck_model})", staff.full_name, part_name]
            )

async def handle_mechanic_action(session: AsyncSession, staff: WorkshopStaff, message_text: str, image_id: str, data: dict, state_step: str = None):
    phone = staff.phone
    text = message_text.strip()

    if state_step == "ws_enter_eta":
        ticket_id = data.get("ticket_id")
        ticket = await get_ticket_with_truck(session, ticket_id)
        if ticket:
            ticket.expected_completion_time = text
            ticket.status = "WITH_MECHANIC"
            await session.commit()
            
            data["ticket_id"] = ticket.ticket_id
            await set_user_state(session, phone, "ws_parts_check", data)
            
            # Notify Ticket Raiser of ETA
            if ticket.logged_by_staff_id:
                raiser = await session.get(WorkshopStaff, ticket.logged_by_staff_id)
                if raiser:
                    truck_num = ticket.truck.truck_number if ticket.truck else ""
                    await meta_api.send_text_message(
                        raiser.phone,
                        f"⏱️ *Workshop ETA Recorded*\n"
                        f"🎫 Ticket: `{ticket.ticket_number}` (Truck #{truck_num})\n"
                        f"👨‍🔧 Mechanic: {staff.full_name}\n"
                        f"📅 Estimated Ready: *{text}*"
                    )

            msg = f"✅ ETA recorded: *{text}*\n\n📦 *Are replacement parts needed from Purchasing?*"
            buttons = [
                {"id": f"btn_ws_parts_none_{ticket.ticket_id}", "title": "In Stocks"},
                {"id": f"btn_ws_parts_req_{ticket.ticket_id}", "title": "Request Parts"}
            ]
            await meta_api.send_button_message(phone, msg, buttons, header_text="PARTS CHECK")
        return True

    if text.startswith("btn_ws_parts_none_") or "in stocks" in text.lower() or "no parts" in text.lower():
        ticket_id = int(text.split("_")[-1])
        ticket = await get_ticket_with_truck(session, ticket_id)
        if ticket:
            ticket.status = "REPAIR_IN_PROGRESS"
            await session.commit()
            await clear_user_state(session, phone)
            
            msg = (
                f"✅ Repair in progress for Ticket `{ticket.ticket_number}`.\n\n"
                f"Tap below once wrenching is completed on the floor:"
            )
            buttons = [{"id": f"btn_ws_repair_done_{ticket.ticket_id}", "title": "🏁 Repair Completed"}]
            await meta_api.send_button_message(phone, msg, buttons, header_text="WORK IN PROGRESS")
        return True

    if text.startswith("btn_ws_parts_req_") or "request parts" in text.lower():
        ticket_id = int(text.split("_")[-1])
        await set_user_state(session, phone, "ws_enter_part_details", {"ticket_id": ticket_id})
        msg = (
            f"🛒 *Parts Requisition:*\n\n"
            f"Please type the required part name, part number, or description:"
        )
        await meta_api.send_text_message(phone, msg)
        return True

    if state_step == "ws_enter_part_details":
        data["part_name"] = text
        data["part_description"] = text
        if image_id:
            data["sample_image_id"] = image_id
            await finalize_parts_request(session, staff, data)
            return True
            
        await set_user_state(session, phone, "ws_parts_attach_photo", data)
        photo_prompt = (
            f"📸 *Attach Sample Photo (Optional)*\n\n"
            f"Please send a sample photo of the required part, or tap below to skip:"
        )
        buttons = [{"id": "btn_ws_skip_mech_photo", "title": "Skip Photo"}]
        await meta_api.send_button_message(phone, photo_prompt, buttons, header_text="PHOTO ATTACHMENT")
        return True

    if state_step == "ws_parts_attach_photo" or text.startswith("btn_ws_skip_mech_photo"):
        if image_id:
            data["sample_image_id"] = image_id
        elif text and text.lower() in {"skip", "skip photo"} or text.startswith("btn_ws_skip_mech_photo"):
            data["sample_image_id"] = None
            
        await finalize_parts_request(session, staff, data)
        return True

    if state_step == "ws_parts_clarification_reply":
        req_id = data.get("request_id")
        parts_req = await session.get(WorkshopPartsRequest, req_id)
        if parts_req:
            parts_req.clarification_response = text
            parts_req.clarification_image_id = image_id
            parts_req.status = "PENDING"
            
            ticket = await get_ticket_with_truck(session, parts_req.ticket_id)
            if ticket:
                ticket.status = "AWAITING_PARTS"
            await session.commit()
            await clear_user_state(session, phone)
            
            await meta_api.send_text_message(phone, "✅ Clarification response sent to Purchasing Team!")
            
            stmt = select(WorkshopStaff).where(WorkshopStaff.role == "PURCHASING", WorkshopStaff.active == True)
            purchasing_team = (await session.execute(stmt)).scalars().all()
            for p in purchasing_team:
                p_update = (
                    f"🔔 *CLARIFICATION RECEIVED FROM MECHANIC*\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🎫 *Ticket ID:* `{ticket.ticket_number if ticket else ''}`\n"
                    f"📦 *Part:* {parts_req.part_name}\n"
                    f"📝 *Mechanic Reply:* {text}\n"
                    f"🖼️ *Photo:* {'Attached' if image_id else 'None'}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"Please confirm action:"
                )
                buttons = [
                    {"id": f"btn_parts_received_{parts_req.request_id}", "title": "📦 Part Received"},
                    {"id": f"btn_parts_need_info_{parts_req.request_id}", "title": "❓ Need Info/Sample"}
                ]
                await meta_api.send_button_message(p.phone, p_update, buttons, header_text="PARTS UPDATE")
        return True

    if text.startswith("btn_ws_repair_done_") or "repair completed" in text.lower() or "repair complete" in text.lower():
        ticket_id = int(text.split("_")[-1])
        ticket = await get_ticket_with_truck(session, ticket_id)
        if ticket:
            now = datetime.datetime.utcnow()
            ticket.repair_completed_at = now
            ticket.sla_result = "ON_TIME"
            await session.commit()
            
            await set_user_state(session, phone, "ws_enter_resolution_notes", {"ticket_id": ticket.ticket_id})
            prompt = (
                f"🏁 *Repair Completed Logged!*\n"
                f"⏱️ Finished at: {now.strftime('%H:%M UTC')}\n"
                f"🟢 *SLA Result:* ON TIME\n\n"
                f"📝 *Please enter detailed Resolution Notes (what was repaired/replaced):*"
            )
            await meta_api.send_text_message(phone, prompt)
        return True

    if state_step == "ws_enter_resolution_notes":
        ticket_id = data.get("ticket_id")
        ticket = await get_ticket_with_truck(session, ticket_id)
        if ticket:
            ticket.resolution_notes = text
            await session.commit()
            
            data["ticket_id"] = ticket.ticket_id
            await set_user_state(session, phone, "ws_enter_costing", data)
            
            prompt = (
                f"💵 *Please enter the Repair Costing Breakdown:*\n\n"
                f"Example: `Parts: $140, Labour: $30, Total: $170` (or total amount):"
            )
            await meta_api.send_text_message(phone, prompt)
        return True

    if state_step == "ws_enter_costing":
        ticket_id = data.get("ticket_id")
        ticket = await get_ticket_with_truck(session, ticket_id)
        if ticket:
            ticket.cost_total = text
            ticket.status = "AWAITING_TEST"
            await session.commit()
            await clear_user_state(session, phone)
            
            await meta_api.send_text_message(
                phone,
                f"✅ Costing recorded: *{text}*\n⏳ Ticket `{ticket.ticket_number}` forwarded to Edward (Supervisor) for Road-Test QC."
            )
            
            stmt = select(WorkshopStaff).where(WorkshopStaff.role == "SUPERVISOR", WorkshopStaff.active == True)
            supervisors = (await session.execute(stmt)).scalars().all()
            truck_num = ticket.truck.truck_number if ticket.truck else ""
            truck_model = ticket.truck.model_make if ticket.truck else ""
            
            for sup in supervisors:
                qc_alert = (
                    f"🚗 *VEHICLE READY FOR QC TESTING*\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🎫 *Ticket ID:* `{ticket.ticket_number}`\n"
                    f"🚚 *Vehicle:* Truck #{truck_num} ({truck_model})\n"
                    f"👨‍🔧 *Repaired By:* {staff.full_name}\n"
                    f"⏱️ *SLA:* 🟢 {ticket.sla_result}\n"
                    f"📝 *Work Done:* {ticket.resolution_notes}\n"
                    f"💵 *Costing:* {ticket.cost_total}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"Did the vehicle pass inspection & road test?"
                )
                buttons = [
                    {"id": f"btn_ws_qc_pass_{ticket.ticket_id}", "title": "✅ Passed Test"},
                    {"id": f"btn_ws_qc_fail_{ticket.ticket_id}", "title": "⚠️ Failed / Rework"}
                ]
                await meta_api.send_button_message(
                    sup.phone,
                    qc_alert,
                    buttons,
                    header_text="QC ROAD-TEST",
                    fallback_template="workshop_qc_alert",
                    template_params=[sup.full_name, ticket.ticket_number, f"Truck #{truck_num} ({truck_model})", ticket.resolution_notes, str(ticket.cost_total)]
                )
        return True

    return False
