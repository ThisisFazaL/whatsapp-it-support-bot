import re
import datetime
import asyncio
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Ticket, SupportAdmin, Employee, TicketStatus, TicketAssignment
from app.state_manager import is_admin, set_user_state, clear_user_state
from app.meta_api import meta_api

STATUS_NAMES = {
    1: "🟡 Open",
    2: "🔵 In Progress",
    3: "🟢 Resolved",
    4: "⚪ Closed"
}

async def handle_admin_command(session: AsyncSession, sender_phone: str, message_text: str) -> bool:
    """
    Checks if message is an admin command (greeting, menu button, accept, or resolve command).
    Returns True if handled, False otherwise.
    """
    text_strip = message_text.strip()
    text_lower = text_strip.lower()
    
    # Match ACCEPT / CLAIM command: "accept TKT-...", "claim_TKT-...", "claim 1"
    claim_match = re.match(r"^(?:accept|claim)[_\s]+([A-Z0-9-]+)$", text_strip, re.IGNORECASE)
    # Match RESOLVE command: "resolve TKT-...", "resolve_TKT-...", "resolve 1"
    resolve_match = re.match(r"^resolve[_\s]+([A-Z0-9-]+)$", text_strip, re.IGNORECASE)

    is_greeting = text_lower in ("hi", "hello", "menu", "admin", "start", "help", "hey")
    is_view_assigned = text_lower in ("cmd_my_assigned_tickets", "my assigned tickets", "assigned tickets", "view tickets", "my tickets")
    is_summary = text_lower in ("cmd_admin_summary_report", "summary report", "summary", "my summary")
    is_raise_cmd = text_lower in ("cmd_raise_ticket", "raise ticket")

    if not claim_match and not resolve_match and not is_greeting and not is_view_assigned and not is_summary and not is_raise_cmd:
        return False

    # Check if sender is an executive observer
    from app.config import settings
    if sender_phone in settings.executive_observer_phones and sender_phone != settings.master_admin_phone:
        if claim_match or resolve_match:
            await meta_api.send_text_message(
                sender_phone,
                "⚠️ *Access Denied*: You are registered as an Executive Observer. Only assigned Support Admins or Master Admin can resolve tickets."
            )
            return True

    # Check if sender is an active support admin
    admin = await is_admin(session, sender_phone)
    if not admin:
        return False  # Pass through to standard employee logic if not an admin

    # ----------------------------------------------------
    # 1. HANDLE ADMIN GREETING / MENU ("Hi", "Hello", "Menu")
    # ----------------------------------------------------
    if is_greeting:
        header = "🛠️ IT SUPPORT ADMIN PORTAL"
        body = (
            f"Hello *{admin.full_name}*! 👋\n\n"
            f"Welcome to the Tagoneswa IT Support Admin Dashboard.\n\n"
            f"Please select an option below to manage your tickets:"
        )
        footer = "Tap a button to proceed"
        buttons = [
            {
                "id": "cmd_my_assigned_tickets",
                "title": "📋 My Assigned Tickets"
            },
            {
                "id": "cmd_admin_summary_report",
                "title": "📊 Summary Report"
            },
            {
                "id": "cmd_raise_ticket",
                "title": "➕ Raise IT Ticket"
            }
        ]
        await meta_api.send_button_message(
            to_phone=sender_phone,
            body_text=body,
            buttons=buttons,
            header_text=header,
            footer_text=footer
        )
        return True

    # ----------------------------------------------------
    # 2. HANDLE "MY ASSIGNED TICKETS" BUTTON CLICK
    # ----------------------------------------------------
    if is_view_assigned:
        asg_stmt = (
            select(TicketAssignment)
            .options(
                selectinload(TicketAssignment.ticket).selectinload(Ticket.employee),
                selectinload(TicketAssignment.ticket).selectinload(Ticket.category),
                selectinload(TicketAssignment.ticket).selectinload(Ticket.subcategory),
                selectinload(TicketAssignment.ticket).selectinload(Ticket.issue_type),
                selectinload(TicketAssignment.ticket).selectinload(Ticket.priority)
            )
            .where(TicketAssignment.admin_id == admin.admin_id)
        )
        asgs = (await session.execute(asg_stmt)).scalars().all()
        tickets = [a.ticket for a in asgs if a.ticket and a.ticket.status_id in (1, 2, 3)]

        if not tickets:
            no_t_msg = f"📋 *IT SUPPORT TICKETS ASSIGNED TO YOU*\n\nHello {admin.full_name},\nYou currently have *0 active tickets* assigned to you. Great job!"
            await meta_api.send_text_message(sender_phone, no_t_msg)
            return True

        summary_header = f"📋 *IT SUPPORT TICKETS ASSIGNED TO YOU ({len(tickets)} Active)*\n\nHello {admin.full_name},\nHere are your current active IT support tickets:"
        await meta_api.send_text_message(sender_phone, summary_header)
        await asyncio.sleep(0.5)

        for t in tickets:
            emp = t.employee
            emp_name = emp.full_name if emp else "Unknown"
            emp_phone = emp.phone if emp else ""
            cat_name = t.category.category_name if t.category else "N/A"
            sub_name = t.subcategory.subcategory_name if t.subcategory else "N/A"
            issue_name = t.issue_type.issue_name if t.issue_type else "Custom Issue"
            p_name = t.priority.priority_name if t.priority else "Medium"
            status_str = STATUS_NAMES.get(t.status_id, "🟡 Open")

            img_line = f"\n🖼️ *Photo Attachment ID:* `{t.image_id}`" if t.image_id else ""

            header = f"🎫 TICKET {t.ticket_number}"
            body = (
                f"👤 *Employee:* {emp_name} (`+{emp_phone}`)\n"
                f"📌 *Category:* {cat_name} ➡️ {sub_name}\n"
                f"⚙️ *Issue:* {issue_name}\n"
                f"🚨 *Priority:* {p_name} | Status: *{status_str}*\n"
                f"📝 *Description:* {t.description}{img_line}"
            )
            footer = "Tap button below once resolved"
            buttons = [
                {
                    "id": f"resolve_{t.ticket_number}",
                    "title": "✅ Mark Resolved"
                }
            ]
            await meta_api.send_button_message(
                to_phone=sender_phone,
                body_text=body,
                buttons=buttons,
                header_text=header,
                footer_text=footer
            )
            await asyncio.sleep(0.8)
        return True

    # ----------------------------------------------------
    # 3. HANDLE "SUMMARY REPORT" BUTTON CLICK
    # ----------------------------------------------------
    if is_summary:
        asg_stmt = (
            select(TicketAssignment)
            .options(selectinload(TicketAssignment.ticket))
            .where(TicketAssignment.admin_id == admin.admin_id)
        )
        asgs = (await session.execute(asg_stmt)).scalars().all()
        tickets = [a.ticket for a in asgs if a.ticket]

        total = len(tickets)
        resolved = sum(1 for t in tickets if t.status_id in (3, 4))
        pending = sum(1 for t in tickets if t.status_id in (1, 2))

        report_msg = (
            f"📊 *MY SUPPORT PERFORMANCE SUMMARY*\n\n"
            f"👤 Admin: *{admin.full_name}*\n"
            f"------------------------------------\n"
            f"• Total Assigned Tickets: *{total}*\n"
            f"• 🟢 Resolved / Closed: *{resolved}*\n"
            f"• 🟡 Pending Action: *{pending}*\n"
            f"------------------------------------\n"
            f"💡 Reply `Hi` anytime to access this admin portal menu."
        )
        await meta_api.send_text_message(sender_phone, report_msg)
        return True

    # ----------------------------------------------------
    # 4. HANDLE "RAISE TICKET" BUTTON CLICK
    # ----------------------------------------------------
    if is_raise_cmd:
        await clear_user_state(session, sender_phone)
        await meta_api.send_text_message(sender_phone, "🆕 Starting new ticket creation flow...")
        return False # Fallthrough to flow handler

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
        asg_stmt = (
            select(TicketAssignment)
            .options(selectinload(TicketAssignment.admin))
            .where(TicketAssignment.ticket_id == ticket.ticket_id)
        )
        asg_res = await session.execute(asg_stmt)
        existing_assignment = asg_res.scalars().first()

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
        await session.execute(delete(TicketAssignment).where(TicketAssignment.ticket_id == ticket.ticket_id))
        
        new_assignment = TicketAssignment(
            ticket_id=ticket.ticket_id,
            admin_id=admin.admin_id
        )
        session.add(new_assignment)
        
        ticket.status_id = 2
        ticket.updated_at = datetime.datetime.utcnow()
        await session.commit()

        await meta_api.send_text_message(
            sender_phone,
            f"✅ *Ticket Claimed Successfully!*\n\n"
            f"You are now assigned to Ticket *{ticket.ticket_number}*.\n"
            f"👤 Employee: {ticket.employee.full_name if ticket.employee else 'N/A'}\n"
            f"📝 Issue: {ticket.description}\n\n"
            f"💡 *Action:* Reply `resolve {ticket.ticket_number}` once resolved."
        )

        if ticket.employee:
            emp_msg = (
                f"🔔 *IT Support Ticket Update*\n\n"
                f"Your support ticket *{ticket.ticket_number}* has been accepted by **{admin.full_name}** (`+{admin.phone}`).\n\n"
                f"Status: 🔵 *IN PROGRESS*\n"
                f"Our support engineer is working on your request."
            )
            await meta_api.send_text_message(ticket.employee.phone, emp_msg)

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

        asg_chk = select(TicketAssignment).where(TicketAssignment.ticket_id == ticket.ticket_id)
        current_asg = (await session.execute(asg_chk)).scalars().first()
        if not current_asg:
            session.add(TicketAssignment(ticket_id=ticket.ticket_id, admin_id=admin.admin_id))

        ticket.status_id = 3 # Resolved
        ticket.updated_at = datetime.datetime.utcnow()
        await session.commit()

        if ticket.employee:
            await set_user_state(
                session=session,
                phone=ticket.employee.phone,
                current_step="awaiting_resolution_confirmation",
                current_data={
                    "ticket_id": ticket.ticket_id,
                    "ticket_number": ticket.ticket_number
                },
                flow_name="resolution_confirmation"
            )

            emp_header = "🔔 TICKET RESOLUTION CONFIRMATION"
            emp_body = (
                f"Your support ticket *{ticket.ticket_number}* has been marked as **RESOLVED** by IT Support Admin ({admin.full_name}).\n\n"
                f"Please confirm if your issue has been completely fixed."
            )
            emp_footer = "Tap a button below to respond"
            emp_buttons = [
                {
                    "id": "confirm_close_ticket",
                    "title": "✅ Confirm & Close"
                },
                {
                    "id": "reopen_ticket",
                    "title": "🔄 Reopen Ticket"
                }
            ]
            await meta_api.send_button_message(
                to_phone=ticket.employee.phone,
                body_text=emp_body,
                buttons=emp_buttons,
                header_text=emp_header,
                footer_text=emp_footer
            )

        admin_msg = (
            f"✅ *Ticket Marked as Resolved*\n\n"
            f"Ticket: *{ticket.ticket_number}*\n"
            f"Employee: {ticket.employee.full_name if ticket.employee else 'N/A'}\n"
            f"Resolution confirmation prompt sent to employee."
        )
        await meta_api.send_text_message(sender_phone, admin_msg)

        if settings.master_admin_phone and sender_phone != settings.master_admin_phone:
            master_resolved = (
                f"✅ *[MASTER ALERT] TICKET RESOLVED*\n\n"
                f"🎫 *Ticket ID:* `{ticket.ticket_number}`\n"
                f"👤 *Employee:* {ticket.employee.full_name if ticket.employee else 'N/A'}\n"
                f"👤 *Resolved By Admin:* {admin.full_name} (`+{admin.phone}`)\n"
                f"📊 *Status:* 🔵 RESOLVED"
            )
            await meta_api.send_text_message(settings.master_admin_phone, master_resolved)

        observer_resolved = (
            f"✅ *[EXECUTIVE OBSERVER ALERT] TICKET RESOLVED*\n\n"
            f"🎫 *Ticket ID:* `{ticket.ticket_number}`\n"
            f"👤 *Employee:* {ticket.employee.full_name if ticket.employee else 'N/A'}\n"
            f"👤 *Resolved By Admin:* {admin.full_name} (`+{admin.phone}`)\n"
            f"📊 *Status:* 🔵 RESOLVED (Awaiting employee confirmation)"
        )

        for obs_phone in settings.executive_observer_phones:
            if obs_phone != settings.master_admin_phone and obs_phone != sender_phone:
                await meta_api.send_text_message(obs_phone, observer_resolved)

        return True

    return False
