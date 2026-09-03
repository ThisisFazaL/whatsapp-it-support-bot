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

async def handle_purchasing_action(session: AsyncSession, staff: WorkshopStaff, message_text: str, data: dict, state_step: str = None):
    phone = staff.phone
    text = message_text.strip()
    
    if state_step == "ws_purchasing_inquiry":
        req_id = data.get("request_id")
        parts_req = await session.get(WorkshopPartsRequest, req_id)
        if parts_req:
            parts_req.status = "INFO_REQUESTED"
            parts_req.clarification_requested = True
            parts_req.clarification_note = text
            
            ticket = await get_ticket_with_truck(session, parts_req.ticket_id)
            if ticket:
                ticket.status = "INFO_REQUESTED"
            await session.commit()
            await clear_user_state(session, phone)
            
            await meta_api.send_text_message(
                phone,
                f"⚠️ Clarification request sent to workshop mechanic.\n📝 *Inquiry:* {text}"
            )
            
            if ticket and ticket.assigned_mechanic_id:
                mechanic = await session.get(WorkshopStaff, ticket.assigned_mechanic_id)
                if mechanic:
                    mech_msg = (
                        f"⚠️ *PURCHASING CLARIFICATION NEEDED*\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🎫 *Ticket ID:* `{ticket.ticket_number}`\n"
                        f"📦 *Part:* {parts_req.part_name}\n"
                        f"📝 *Purchasing Note:* {text}\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"💡 Please reply directly with the OEM part number or upload a clearer sample photo:"
                    )
                    await set_user_state(session, mechanic.phone, "ws_parts_clarification_reply", {"request_id": parts_req.request_id, "ticket_id": ticket.ticket_id})
                    await meta_api.send_text_message(mechanic.phone, mech_msg)
        return True

    if text.startswith("btn_parts_need_info_") or "need info" in text.lower() or "need sample" in text.lower():
        req_id = int(text.split("_")[-1])
        await set_user_state(session, phone, "ws_purchasing_inquiry", {"request_id": req_id})
        prompt = (
            f"📝 *Specify Information Required:*\n\n"
            f"Please type what additional info, OEM serial numbers, or physical samples are needed from the mechanic:"
        )
        await meta_api.send_text_message(phone, prompt)
        return True

    if text.startswith("btn_parts_received_") or "part received" in text.lower() or "parts received" in text.lower():
        req_id = int(text.split("_")[-1])
        parts_req = await session.get(WorkshopPartsRequest, req_id)
        if parts_req:
            now = datetime.datetime.utcnow()
            parts_req.status = "RECEIVED"
            parts_req.received_at = now
            
            ticket = await get_ticket_with_truck(session, parts_req.ticket_id)
            if ticket:
                ticket.status = "REPAIR_IN_PROGRESS"
            await session.commit()
            await clear_user_state(session, phone)
            
            await meta_api.send_text_message(
                phone,
                f"✅ Part receipt recorded for Ticket `{ticket.ticket_number if ticket else ''}`.\nStatus updated to *REPAIR IN PROGRESS*."
            )
            
            if ticket and ticket.assigned_mechanic_id:
                mechanic = await session.get(WorkshopStaff, ticket.assigned_mechanic_id)
                if mechanic:
                    mech_alert = (
                        f"📦 *PART DELIVERED TO WORKSHOP!*\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🎫 *Ticket ID:* `{ticket.ticket_number}`\n"
                        f"📦 *Part:* {parts_req.part_name}\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"Please proceed with physical repair on shop floor. Tap completion when done:"
                    )
                    buttons = [{"id": f"btn_ws_repair_done_{ticket.ticket_id}", "title": "🏁 Repair Completed"}]
                    await meta_api.send_button_message(mechanic.phone, mech_alert, buttons, header_text="JOB READY")
        return True

    return False
