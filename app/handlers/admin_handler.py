import re
import datetime
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Ticket, SupportAdmin, Employee, TicketStatus
from app.state_manager import is_admin, set_user_state
from app.meta_api import meta_api

async def handle_admin_command(session: AsyncSession, sender_phone: str, message_text: str) -> bool:
    """
    Checks if message is an admin command (e.g. 'resolve TKT-20260812-00001').
    Returns True if handled, False otherwise.
    """
    text_strip = message_text.strip()
    match = re.match(r"^resolve\s+(TKT-[A-Z0-9-]+)$", text_strip, re.IGNORECASE)
    if not match:
        return False
    
    ticket_number = match.group(1).upper()

    # Verify if sender is an admin
    admin = await is_admin(session, sender_phone)
    if not admin:
        await meta_api.send_text_message(
            sender_phone,
            "⚠️ *Access Denied*: You are not authorized as an IT Support Admin to resolve tickets."
        )
        return True

    # Find the ticket
    stmt = (
        select(Ticket)
        .options(selectinload(Ticket.employee))
        .where(Ticket.ticket_number == ticket_number)
    )
    res = await session.execute(stmt)
    ticket = res.scalars().first()

    if not ticket:
        await meta_api.send_text_message(
            sender_phone,
            f"❌ *Ticket Not Found*: No ticket found matching `{ticket_number}`."
        )
        return True

    if ticket.status_id in (3, 4):
        # Already resolved or closed
        status_name = "Resolved" if ticket.status_id == 3 else "Closed"
        await meta_api.send_text_message(
            sender_phone,
            f"ℹ️ Ticket *{ticket_number}* is already marked as **{status_name}**."
        )
        return True

    # Update ticket status to Resolved (status_id = 3)
    ticket.status_id = 3
    ticket.updated_at = datetime.datetime.utcnow()
    await session.commit()

    employee = ticket.employee

    # Update Employee state to awaiting_resolution_confirmation
    if employee:
        await set_user_state(
            session=session,
            phone=employee.phone,
            current_step="awaiting_resolution_confirmation",
            current_data={
                "ticket_id": ticket.ticket_id,
                "ticket_number": ticket.ticket_number
            },
            flow_name="resolution_confirmation"
        )

        # Notify Employee via WhatsApp
        emp_msg = (
            f"🔔 *IT Support Ticket Update*\n\n"
            f"Your support ticket *{ticket.ticket_number}* has been marked as **RESOLVED** by IT Admin ({admin.full_name}).\n\n"
            f"Please confirm if your issue is fixed by replying:\n"
            f"1️⃣ Reply *1* to Confirm & Close Ticket\n"
            f"2️⃣ Reply *2* to Reopen Ticket"
        )
        await meta_api.send_text_message(employee.phone, emp_msg)

    # Notify Admin
    admin_msg = (
        f"✅ *Ticket Marked as Resolved*\n\n"
        f"Ticket: *{ticket.ticket_number}*\n"
        f"Employee: {employee.full_name if employee else 'N/A'}\n"
        f"Resolution confirmation prompt sent to employee."
    )
    await meta_api.send_text_message(sender_phone, admin_msg)

    return True
