import datetime
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Ticket, TicketAssignment, SupportAdmin
from app.state_manager import clear_user_state
from app.meta_api import meta_api

async def handle_resolution_confirmation(
    session: AsyncSession,
    sender_phone: str,
    message_text: str,
    current_data: dict
) -> bool:
    """
    Processes employee response when awaiting resolution confirmation.
    Returns True when processed.
    """
    ticket_id = current_data.get("ticket_id")
    ticket_number = current_data.get("ticket_number")

    if not ticket_id:
        await clear_user_state(session, sender_phone)
        await meta_api.send_text_message(sender_phone, "Ticket context missing. State reset.")
        return True

    # Retrieve ticket details
    stmt = (
        select(Ticket)
        .options(selectinload(Ticket.employee))
        .where(Ticket.ticket_id == ticket_id)
    )
    res = await session.execute(stmt)
    ticket = res.scalars().first()

    if not ticket:
        await clear_user_state(session, sender_phone)
        await meta_api.send_text_message(sender_phone, "Ticket no longer exists. State reset.")
        return True

    choice = message_text.strip()

    if choice == "1":
        # 1 = Close Ticket (status_id = 4)
        ticket.status_id = 4
        ticket.closed_at = datetime.datetime.utcnow()
        ticket.updated_at = datetime.datetime.utcnow()
        await session.commit()
        await clear_user_state(session, sender_phone)

        # Notify Employee
        await meta_api.send_text_message(
            sender_phone,
            f"🎉 *Ticket Closed*\n\nThank you for confirming! Ticket *{ticket_number}* is now officially **CLOSED**."
        )

        # Notify Assigned Admin
        assign_stmt = (
            select(TicketAssignment)
            .options(selectinload(TicketAssignment.admin))
            .where(TicketAssignment.ticket_id == ticket.ticket_id)
        )
        assign_res = await session.execute(assign_stmt)
        assignment = assign_res.scalars().first()
        if assignment and assignment.admin:
            await meta_api.send_text_message(
                assignment.admin.phone,
                f"ℹ️ *Ticket Resolution Confirmed*\n\n"
                f"Employee {ticket.employee.full_name} confirmed resolution for Ticket *{ticket_number}*. Ticket is now CLOSED."
            )

        # Notify Master Group of Ticket Closed
        master_group_closed = (
            f"🎉 *[MASTER GROUP ALERT] TICKET OFFICIALLY CLOSED*\n\n"
            f"🎫 *Ticket ID:* `{ticket_number}`\n"
            f"👤 *Employee:* {ticket.employee.full_name if ticket.employee else 'N/A'}\n"
            f"📊 *Status:* ⚪ CLOSED (Resolution Confirmed by Employee)"
        )

        from app.config import settings
        master_stmt = select(SupportAdmin).where(SupportAdmin.is_master_admin == True, SupportAdmin.active == True)
        master_admins = (await session.execute(master_stmt)).scalars().all()
        notified_phones = set()

        if settings.master_group_phone:
            await meta_api.send_text_message(settings.master_group_phone, master_group_closed)
            notified_phones.add(settings.master_group_phone)

        for master in master_admins:
            if master.phone not in notified_phones:
                await meta_api.send_text_message(master.phone, master_group_closed)
                notified_phones.add(master.phone)

        return True

    elif choice == "2":
        # 2 = Reopen Ticket (status_id = 1)
        ticket.status_id = 1
        ticket.updated_at = datetime.datetime.utcnow()
        await session.commit()
        await clear_user_state(session, sender_phone)

        # Notify Employee
        await meta_api.send_text_message(
            sender_phone,
            f"🔄 *Ticket Reopened*\n\nTicket *{ticket_number}* has been **REOPENED**. Our IT Support team has been notified and will assist you."
        )

        # Notify Assigned Admin
        assign_stmt = (
            select(TicketAssignment)
            .options(selectinload(TicketAssignment.admin))
            .where(TicketAssignment.ticket_id == ticket.ticket_id)
        )
        assign_res = await session.execute(assign_stmt)
        assignment = assign_res.scalars().first()
        if assignment and assignment.admin:
            await meta_api.send_text_message(
                assignment.admin.phone,
                f"🚨 *Ticket Reopened*\n\n"
                f"Employee {ticket.employee.full_name} requested to REOPEN Ticket *{ticket_number}*. Status changed back to **OPEN**."
            )
        return True

    else:
        # Invalid option
        await meta_api.send_text_message(
            sender_phone,
            f"❓ *Invalid Selection*\n\nPlease reply with:\n1️⃣ *1* to Confirm & Close Ticket\n2️⃣ *2* to Reopen Ticket"
        )
        return True
