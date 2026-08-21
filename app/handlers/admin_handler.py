import re
import datetime
import asyncio
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import (
    Ticket, MaintenanceTicket, SupportAdmin, Employee, TicketStatus,
    TicketAssignment, MaintenanceTicketAssignment, ConversationState
)
from app.state_manager import is_admin, set_user_state, clear_user_state, get_user_state
from app.meta_api import meta_api

STATUS_NAMES = {
    1: "🟡 Open",
    2: "🔵 In Progress",
    3: "🟢 Resolved",
    4: "⚪ Closed"
}

async def handle_admin_resolution_note(session: AsyncSession, admin: SupportAdmin, sender_phone: str, message_text: str, state: ConversationState) -> bool:
    """
    Handles resolution note input typed by admin after tapping [ 🟢 Resolve Ticket ].
    """
    if not state or state.flow_name != "admin_resolution" or state.current_step != "awaiting_admin_resolution_note":
        return False

    ticket_id = state.current_data.get("ticket_id") if state.current_data else None
    ticket_num = state.current_data.get("ticket_number", "") if state.current_data else ""
    is_maint = "TKT-MNT" in ticket_num or state.current_data.get("is_maint", False)

    if not ticket_id:
        await clear_user_state(session, sender_phone)
        return False

    if is_maint:
        stmt = (
            select(MaintenanceTicket)
            .options(
                selectinload(MaintenanceTicket.employee),
                selectinload(MaintenanceTicket.category),
                selectinload(MaintenanceTicket.subcategory),
                selectinload(MaintenanceTicket.issue_type)
            )
            .where(MaintenanceTicket.ticket_id == ticket_id)
        )
    else:
        stmt = (
            select(Ticket)
            .options(
                selectinload(Ticket.employee),
                selectinload(Ticket.category),
                selectinload(Ticket.subcategory),
                selectinload(Ticket.issue_type)
            )
            .where(Ticket.ticket_id == ticket_id)
        )

    res = await session.execute(stmt)
    ticket = res.scalars().first()

    if not ticket:
        await clear_user_state(session, sender_phone)
        await meta_api.send_text_message(sender_phone, "❌ Ticket not found.")
        return True

    resolution_note = message_text.strip()
    if len(resolution_note) < 2:
        await meta_api.send_text_message(sender_phone, "⚠️ Resolution note is too short. Please type a brief description of what was done to fix the issue:")
        return True

    # Update Ticket Status & Note
    ticket.status_id = 3 # Resolved
    ticket.resolution_note = resolution_note
    ticket.updated_at = datetime.datetime.utcnow()

    # Assign Admin
    if is_maint:
        asg_chk = select(MaintenanceTicketAssignment).where(MaintenanceTicketAssignment.ticket_id == ticket.ticket_id)
        current_asg = (await session.execute(asg_chk)).scalars().first()
        if not current_asg:
            session.add(MaintenanceTicketAssignment(ticket_id=ticket.ticket_id, admin_id=admin.admin_id))
        else:
            current_asg.admin_id = admin.admin_id
    else:
        asg_chk = select(TicketAssignment).where(TicketAssignment.ticket_id == ticket.ticket_id)
        current_asg = (await session.execute(asg_chk)).scalars().first()
        if not current_asg:
            session.add(TicketAssignment(ticket_id=ticket.ticket_id, admin_id=admin.admin_id))
        else:
            current_asg.admin_id = admin.admin_id

    await session.commit()
    await clear_user_state(session, sender_phone)

    # 1. Notify Employee / Reporter
    if ticket.employee:
        await set_user_state(
            session=session,
            phone=ticket.employee.phone,
            current_step="awaiting_resolution_confirmation",
            current_data={
                "ticket_id": ticket.ticket_id,
                "ticket_number": ticket.ticket_number,
                "is_maint": is_maint
            },
            flow_name="resolution_confirmation"
        )

        cat_name = ticket.category.category_name if ticket.category else "N/A"
        sub_name = ticket.subcategory.subcategory_name if ticket.subcategory else "N/A"
        issue_name = ticket.issue_type.issue_name if ticket.issue_type else "Custom Issue"
        domain_title = "Building Maintenance" if is_maint else "IT Support"

        emp_header = "🔔 TICKET RESOLUTION CONFIRMATION"
        emp_body = (
            f"Your {domain_title} ticket *{ticket.ticket_number}* has been marked as **RESOLVED** by Admin ({admin.full_name}).\n\n"
            f"📌 *Category:* {cat_name} ➡️ {sub_name}\n"
            f"⚙️ *Issue:* {issue_name}\n"
            f"📝 *Description:* {ticket.description}\n"
            f"🔧 *Resolution Note:* _{resolution_note}_\n\n"
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
            footer_text=emp_footer,
            image_id=ticket.image_id
        )

    # 2. Confirm to Resolving Admin
    admin_msg = (
        f"✅ *Ticket Marked as Resolved!*\n\n"
        f"🎫 Ticket: *{ticket.ticket_number}*\n"
        f"👤 Reporter: {ticket.employee.full_name if ticket.employee else 'N/A'}\n"
        f"🔧 Note: _{resolution_note}_\n\n"
        f"Resolution confirmation prompt sent to reporter."
    )
    await meta_api.send_text_message(sender_phone, admin_msg)

    # 3. Master Admin Alert
    if settings.master_admin_phone and sender_phone != settings.master_admin_phone:
        cat_name = ticket.category.category_name if ticket.category else "N/A"
        sub_name = ticket.subcategory.subcategory_name if ticket.subcategory else "N/A"
        issue_name = ticket.issue_type.issue_name if ticket.issue_type else "Custom Issue"
        emp_name = ticket.employee.full_name if ticket.employee else "N/A"
        emp_phone = f" (+{ticket.employee.phone})" if ticket.employee else ""

        master_resolved = (
            f"✅ *[MASTER ALERT] TICKET RESOLVED* 🔵\n\n"
            f"🎫 *Ticket ID:* `{ticket.ticket_number}`\n"
            f"👤 *Reporter:* {emp_name}{emp_phone}\n"
            f"📌 *Category:* {cat_name} ➡️ {sub_name}\n"
            f"⚙️ *Issue:* {issue_name}\n"
            f"📝 *Description:* {ticket.description}\n"
            f"🔧 *Resolution Note:* _{resolution_note}_\n\n"
            f"👤 *Resolved By Admin:* {admin.full_name} (`+{admin.phone}`)\n"
            f"📊 *Status:* 🔵 RESOLVED"
        )
        if ticket.image_id:
            await meta_api.send_image_message(settings.master_admin_phone, ticket.image_id, caption=master_resolved)
        else:
            await meta_api.send_text_message(settings.master_admin_phone, master_resolved)

    # 4. Observer Alerts
    observer_resolved = (
        f"✅ *[EXECUTIVE OBSERVER ALERT] TICKET RESOLVED*\n\n"
        f"🎫 *Ticket ID:* `{ticket.ticket_number}`\n"
        f"👤 *Reporter:* {ticket.employee.full_name if ticket.employee else 'N/A'}\n"
        f"🔧 *Note:* _{resolution_note}_\n"
        f"👤 *Resolved By Admin:* {admin.full_name} (`+{admin.phone}`)"
    )

    for obs_phone in settings.executive_observer_phones:
        if obs_phone != settings.master_admin_phone and obs_phone != sender_phone:
            await meta_api.send_text_message(obs_phone, observer_resolved)

    return True

async def handle_admin_command(session: AsyncSession, sender_phone: str, message_text: str) -> bool:
    """
    Checks if message is an admin command (greeting, menu button, accept, or resolve command).
    Returns True if handled, False otherwise.
    """
    text_strip = message_text.strip()
    text_lower = text_strip.lower()

    # Check if sender is an active support admin
    admin = await is_admin(session, sender_phone)
    if not admin:
        return False

    # Check if admin is currently answering resolution note prompt
    state = await get_user_state(session, sender_phone)
    if state and state.flow_name == "admin_resolution" and state.current_step == "awaiting_admin_resolution_note":
        return await handle_admin_resolution_note(session, admin, sender_phone, message_text, state)

    # Match ACCEPT / CLAIM command: "accept TKT-...", "claim_TKT-..."
    claim_match = re.match(r"^(?:accept|claim)[_\s]+([A-Z0-9-]+)$", text_strip, re.IGNORECASE)
    # Match RESOLVE command: "resolve TKT-...", "resolve_TKT-...", "resolve 1"
    resolve_match = re.match(r"^resolve[_\s]+([A-Z0-9-]+)$", text_strip, re.IGNORECASE)

    is_view_assigned = any(k in text_lower for k in ("cmd_my_assigned_tickets", "assigned", "my tickets", "view tickets"))
    is_summary = any(k in text_lower for k in ("cmd_admin_summary_report", "summary", "report"))
    is_raise_cmd = any(k in text_lower for k in ("cmd_raise_ticket", "raise ticket", "raise it ticket"))
    is_greeting = not is_view_assigned and not is_summary and not is_raise_cmd and any(k in text_lower for k in ("hi", "hello", "menu", "admin", "start", "help", "hey"))

    if not claim_match and not resolve_match and not is_greeting and not is_view_assigned and not is_summary and not is_raise_cmd:
        return False

    # Executive Observer check
    if sender_phone in settings.executive_observer_phones and sender_phone != settings.master_admin_phone:
        if claim_match or resolve_match:
            await meta_api.send_text_message(
                sender_phone,
                "⚠️ *Access Denied*: You are registered as an Executive Observer. Only assigned Support Admins or Master Admin can resolve tickets."
            )
            return True

    # 1. HANDLE GREETING / MENU
    if is_greeting:
        await clear_user_state(session, sender_phone)
        header = "🛠️ SUPPORT ADMIN PORTAL"
        body = (
            f"Hello *{admin.full_name}*! 👋\n\n"
            f"Welcome to the Support Admin Dashboard.\n\n"
            f"Please select an option below to manage your tickets:"
        )
        footer = "Tap a button to proceed"
        buttons = [
            {"id": "cmd_my_assigned_tickets", "title": "📋 My Assigned Tickets"},
            {"id": "cmd_admin_summary_report", "title": "📊 Summary Report"},
            {"id": "cmd_raise_ticket", "title": "➕ Create Ticket"}
        ]
        await meta_api.send_button_message(
            to_phone=sender_phone,
            body_text=body,
            buttons=buttons,
            header_text=header,
            footer_text=footer
        )
        return True

    # 2. HANDLE MY ASSIGNED TICKETS
    if is_view_assigned:
        await clear_user_state(session, sender_phone)
        tickets = []

        if admin.is_maintenance_admin or admin.is_master_admin:
            m_asg_stmt = (
                select(MaintenanceTicketAssignment)
                .options(
                    selectinload(MaintenanceTicketAssignment.ticket).selectinload(MaintenanceTicket.employee),
                    selectinload(MaintenanceTicketAssignment.ticket).selectinload(MaintenanceTicket.category),
                    selectinload(MaintenanceTicketAssignment.ticket).selectinload(MaintenanceTicket.subcategory),
                    selectinload(MaintenanceTicketAssignment.ticket).selectinload(MaintenanceTicket.issue_type),
                    selectinload(MaintenanceTicketAssignment.ticket).selectinload(MaintenanceTicket.priority)
                )
                .where(MaintenanceTicketAssignment.admin_id == admin.admin_id)
            )
            m_asgs = (await session.execute(m_asg_stmt)).scalars().all()
            tickets.extend([a.ticket for a in m_asgs if a.ticket and a.ticket.status_id in (1, 2)])

        if not admin.is_maintenance_admin or admin.is_master_admin:
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
            tickets.extend([a.ticket for a in asgs if a.ticket and a.ticket.status_id in (1, 2)])

        if not tickets:
            no_t_msg = f"📋 *ACTIVE TICKETS ASSIGNED TO YOU*\n\nHello {admin.full_name},\nYou currently have *0 active tickets* assigned to you."
            await meta_api.send_text_message(sender_phone, no_t_msg)
            return True

        summary_header = f"📋 *ACTIVE TICKETS ASSIGNED TO YOU ({len(tickets)} Active)*\n\nHello {admin.full_name},\nHere are your current active support tickets:"
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
            domain_label = "🛠️ MAINTENANCE" if getattr(t, "domain", "") == "MAINTENANCE" or "TKT-MNT" in t.ticket_number else "💻 IT"
            room_info = f"\n📍 *Room/Area:* {t.room_area}" if getattr(t, "room_area", None) else ""
            hazard_info = "\n⚠️ *SAFETY HAZARD FLAG!*" if getattr(t, "is_safety_hazard", False) else ""

            header = f"🎫 TICKET {t.ticket_number} ({domain_label})"
            body = (
                f"👤 *Reporter:* {emp_name} (`+{emp_phone}`){room_info}\n"
                f"📌 *Category:* {cat_name} ➡️ {sub_name}\n"
                f"⚙️ *Issue:* {issue_name}\n"
                f"🚨 *Priority:* {p_name} | Status: *{status_str}*{hazard_info}\n"
                f"📝 *Description:* {t.description}"
            )
            footer = "Tap button below to resolve"
            buttons = [
                {
                    "id": f"resolve_{t.ticket_number}",
                    "title": "🟢 Resolve Ticket"
                }
            ]
            await meta_api.send_button_message(
                to_phone=sender_phone,
                body_text=body,
                buttons=buttons,
                header_text=header,
                footer_text=footer,
                image_id=t.image_id
            )
            await asyncio.sleep(0.8)
        return True

    # 3. HANDLE SUMMARY REPORT
    if is_summary:
        await clear_user_state(session, sender_phone)
        total = 0
        resolved = 0
        pending = 0

        if admin.is_maintenance_admin or admin.is_master_admin:
            m_asg_stmt = select(MaintenanceTicketAssignment).options(selectinload(MaintenanceTicketAssignment.ticket)).where(MaintenanceTicketAssignment.admin_id == admin.admin_id)
            m_asgs = (await session.execute(m_asg_stmt)).scalars().all()
            m_tickets = [a.ticket for a in m_asgs if a.ticket]
            total += len(m_tickets)
            resolved += sum(1 for t in m_tickets if t.status_id in (3, 4))
            pending += sum(1 for t in m_tickets if t.status_id in (1, 2))

        if not admin.is_maintenance_admin or admin.is_master_admin:
            asg_stmt = select(TicketAssignment).options(selectinload(TicketAssignment.ticket)).where(TicketAssignment.admin_id == admin.admin_id)
            asgs = (await session.execute(asg_stmt)).scalars().all()
            it_tickets = [a.ticket for a in asgs if a.ticket]
            total += len(it_tickets)
            resolved += sum(1 for t in it_tickets if t.status_id in (3, 4))
            pending += sum(1 for t in it_tickets if t.status_id in (1, 2))

        report_msg = (
            f"📊 *MY SUPPORT PERFORMANCE SUMMARY*\n\n"
            f"👤 Admin: *{admin.full_name}*\n"
            f"------------------------------------\n"
            f"• Total Assigned Tickets: *{total}*\n"
            f"• 🟢 Resolved / Closed: *{resolved}*\n"
            f"• 🟡 Pending Action: *{pending}*\n"
            f"------------------------------------\n"
            f"💡 Reply `Hi` anytime to access your portal."
        )
        await meta_api.send_text_message(sender_phone, report_msg)
        return True

    # 4. HANDLE RAISE TICKET
    if is_raise_cmd:
        await clear_user_state(session, sender_phone)
        await meta_api.send_text_message(sender_phone, "🆕 Starting ticket creation flow...")
        return False

    # 5. HANDLE RESOLVE BUTTON TAP OR COMMAND -> PROMPT FOR NOTES
    raw_ticket_arg = (claim_match or resolve_match).group(1).upper()
    is_maint_ticket = "TKT-MNT" in raw_ticket_arg

    if is_maint_ticket:
        stmt = (
            select(MaintenanceTicket)
            .options(
                selectinload(MaintenanceTicket.employee),
                selectinload(MaintenanceTicket.category),
                selectinload(MaintenanceTicket.subcategory),
                selectinload(MaintenanceTicket.issue_type)
            )
            .where(
                (MaintenanceTicket.ticket_number == raw_ticket_arg) |
                (MaintenanceTicket.ticket_number.endswith(f"-{raw_ticket_arg.zfill(5)}")) |
                (MaintenanceTicket.ticket_number.endswith(raw_ticket_arg))
            )
        )
    else:
        stmt = (
            select(Ticket)
            .options(
                selectinload(Ticket.employee),
                selectinload(Ticket.category),
                selectinload(Ticket.subcategory),
                selectinload(Ticket.issue_type)
            )
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

    if resolve_match:
        if ticket.status_id in (3, 4):
            status_name = "Resolved" if ticket.status_id == 3 else "Closed"
            await meta_api.send_text_message(
                sender_phone,
                f"ℹ️ Ticket *{ticket.ticket_number}* is already marked as **{status_name}**."
            )
            return True

        # Prompt Admin for Resolution Notes (Set Conversation State)
        await set_user_state(
            session=session,
            phone=sender_phone,
            current_step="awaiting_admin_resolution_note",
            current_data={
                "ticket_id": ticket.ticket_id,
                "ticket_number": ticket.ticket_number,
                "is_maint": is_maint_ticket
            },
            flow_name="admin_resolution"
        )

        prompt_msg = (
            f"📝 *RESOLUTION NOTE REQUIRED*\n\n"
            f"You are resolving Ticket *{ticket.ticket_number}*.\n"
            f"Please reply with a brief note describing what was done to fix the issue:\n"
            f"_(e.g., 'Replaced broken door latch and tested clip')_"
        )
        await meta_api.send_text_message(sender_phone, prompt_msg)
        return True

    return False
