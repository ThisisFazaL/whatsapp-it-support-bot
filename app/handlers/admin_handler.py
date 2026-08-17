import re
import datetime
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Ticket, SupportAdmin, Employee, TicketStatus, TicketAssignment
from app.state_manager import is_admin, set_user_state
from app.meta_api import meta_api

async def handle_admin_command(session: AsyncSession, sender_phone: str, message_text: str) -> bool:
    """
    Checks if message is an admin command (e.g., 'accept TKT-20260817-00001' or 'resolve TKT-20260817-00001').
    Returns True if handled, False otherwise.
    """
    text_strip = message_text.strip()
    
    # Match ACCEPT / CLAIM command: "accept TKT-...", "claim_TKT-...", "claim 1"
    claim_match = re.match(r"^(?:accept|claim)[_\s]+([A-Z0-9-]+)$", text_strip, re.IGNORECASE)
    # Match RESOLVE command: "resolve TKT-...", "resolve_TKT-...", "resolve 1"
    resolve_match = re.match(r"^resolve[_\s]+([A-Z0-9-]+)$", text_strip, re.IGNORECASE)

    if not claim_match and not resolve_match:
        return False

    # Verify if sender is an active support admin
    admin = await is_admin(session, sender_phone)
    if not admin:
        await meta_api.send_text_message(
            sender_phone,
            "⚠️ *Access Denied*: You are not registered as an active IT Support Admin."
        )
        return True

    raw_ticket_arg = (claim_match or resolve_match).group(1).upper()
    
    # Flexible ticket search: full "TKT-YYYYMMDD-00001" or partial number/ID "00001" or "1"
    stmt = (
        select(Ticket)
        .options(selectinload(Ticket.employee))
        .where(
            (Ticket.ticket_number == raw_ticket_arg) |
            (Ticket.ticket_number.endswith(f"-{raw_ticket_arg.zfill(5)}")) |
            (Ticket.ticket_number.endswith(raw_ticket_arg))
        )
    )
    res = await session.execute(stmt)
    ticket = res.scalars().first()

    if not ticket:
        await meta_api.send_text_message(
            sender_phone,
            f"❌ *Ticket Not Found*: Could not find any ticket matching `{raw_ticket_arg}`."
        )
        return True

    # ----------------------------------------------------
    # HANDLE ACCEPT / CLAIM COMMAND
    # ----------------------------------------------------
    if claim_match:
        # Check current assignment
        asg_stmt = (
            select(TicketAssignment)
            .options(selectinload(TicketAssignment.admin))
            .where(TicketAssignment.ticket_id == ticket.ticket_id)
        )
        asg_res = await session.execute(asg_stmt)
        existing_assignment = asg_res.scalars().first()

        # If ticket is already claimed by someone else and status is In Progress (2), Resolved (3), or Closed (4)
        if ticket.status_id in (2, 3, 4) and existing_assignment and existing_assignment.admin_id != admin.admin_id:
            claimed_by = existing_assignment.admin.full_name if existing_assignment.admin else "Another Admin"
            claimed_phone = f" (+{existing_assignment.admin.phone})" if existing_assignment.admin else ""
            await meta_api.send_text_message(
                sender_phone,
                f"ℹ️ *Ticket Already Claimed*\n\nTicket *{ticket.ticket_number}* has already been claimed by **{claimed_by}**{claimed_phone}."
            )
            return True

        if existing_assignment and existing_assignment.admin_id == admin.admin_id and ticket.status_id == 2:
            await meta_api.send_text_message(
                sender_phone,
                f"ℹ️ You have already claimed Ticket *{ticket.ticket_number}*.\n💡 Reply `resolve {ticket.ticket_number}` when fixed."
            )
            return True

        # Claim the ticket!
        # Clear old assignment if any
        await session.execute(delete(TicketAssignment).where(TicketAssignment.ticket_id == ticket.ticket_id))
        
        new_assignment = TicketAssignment(
            ticket_id=ticket.ticket_id,
            admin_id=admin.admin_id
        )
        session.add(new_assignment)
        
        # Change status to In Progress (status_id = 2)
        ticket.status_id = 2
        ticket.updated_at = datetime.datetime.utcnow()
        await session.commit()

        # 1. Confirm to Claiming Admin
        await meta_api.send_text_message(
            sender_phone,
            f"✅ *Ticket Claimed Successfully!*\n\n"
            f"You are now assigned to Ticket *{ticket.ticket_number}*.\n"
            f"👤 Employee: {ticket.employee.full_name if ticket.employee else 'N/A'}\n"
            f"📝 Issue: {ticket.description}\n\n"
            f"💡 *Action:* Reply `resolve {ticket.ticket_number}` once resolved."
        )

        # 2. Notify Employee on WhatsApp
        if ticket.employee:
            emp_msg = (
                f"🔔 *IT Support Ticket Update*\n\n"
                f"Your support ticket *{ticket.ticket_number}* has been accepted by **{admin.full_name}** (`+{admin.phone}`).\n\n"
                f"Status: 🔵 *IN PROGRESS*\n"
                f"Our support engineer is working on your request."
            )
            await meta_api.send_text_message(ticket.employee.phone, emp_msg)

        # 3. Notify Other Active Admins that ticket is claimed
        other_admins_stmt = select(SupportAdmin).where(SupportAdmin.active == True, SupportAdmin.admin_id != admin.admin_id)
        other_admins = (await session.execute(other_admins_stmt)).scalars().all()
        for o_admin in other_admins:
            broadcast_claimed = f"ℹ️ Ticket *{ticket.ticket_number}* was claimed by **{admin.full_name}**."
            await meta_api.send_text_message(o_admin.phone, broadcast_claimed)

        return True

    # ----------------------------------------------------
    # HANDLE RESOLVE COMMAND
    # ----------------------------------------------------
    if resolve_match:
        if ticket.status_id in (3, 4):
            status_name = "Resolved" if ticket.status_id == 3 else "Closed"
            await meta_api.send_text_message(
                sender_phone,
                f"ℹ️ Ticket *{ticket.ticket_number}* is already marked as **{status_name}**."
            )
            return True

        # Ensure ticket assignment is logged to this admin if resolving directly
        asg_chk = select(TicketAssignment).where(TicketAssignment.ticket_id == ticket.ticket_id)
        current_asg = (await session.execute(asg_chk)).scalars().first()
        if not current_asg:
            session.add(TicketAssignment(ticket_id=ticket.ticket_id, admin_id=admin.admin_id))

        ticket.status_id = 3 # Resolved
        ticket.updated_at = datetime.datetime.utcnow()
        await session.commit()

        employee = ticket.employee
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

        # Notify Master Group of Ticket Resolution
        master_group_resolved = (
            f"✅ *[MASTER GROUP ALERT] TICKET RESOLVED*\n\n"
            f"🎫 *Ticket ID:* `{ticket.ticket_number}`\n"
            f"👤 *Employee:* {employee.full_name if employee else 'N/A'}\n"
            f"👤 *Resolved By Admin:* {admin.full_name} (`+{admin.phone}`)\n"
            f"📊 *Status:* 🔵 RESOLVED (Awaiting employee confirmation)"
        )

        from app.config import settings
        master_stmt = select(SupportAdmin).where(SupportAdmin.is_master_admin == True, SupportAdmin.active == True)
        master_admins = (await session.execute(master_stmt)).scalars().all()
        notified_phones = set()

        if settings.master_group_phone:
            await meta_api.send_text_message(settings.master_group_phone, master_group_resolved)
            notified_phones.add(settings.master_group_phone)

        for master in master_admins:
            if master.phone not in notified_phones:
                await meta_api.send_text_message(master.phone, master_group_resolved)
                notified_phones.add(master.phone)

        return True

    return False
