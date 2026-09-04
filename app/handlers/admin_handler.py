import re
import datetime
import asyncio
import logging
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("admin_handler")

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
    if resolution_note.lower().startswith(("resolve_", "claim_", "cmd_", "btn_", "confirm_", "reopen_")):
        logger.warning(f"Ignored button payload '{resolution_note}' as resolution note text.")
        return False

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
        domain_title = "Building Projects" if is_maint else "IT Support"

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

async def deliver_pending_unclaimed_tickets_to_admin(session: AsyncSession, admin: SupportAdmin, sender_phone: str):
    """
    Delivers all open, unclaimed pending tickets (from the period when 24h window was closed)
    to the admin whenever they send 'hi' or open the bot dashboard.
    """
    try:
        unclaimed_maint = []
        unclaimed_it = []

        # 1. Projects / Maintenance Domain Unclaimed Tickets
        if admin.is_maintenance_admin or admin.is_master_admin:
            m_assigned_subq = select(MaintenanceTicketAssignment.ticket_id)
            m_stmt = (
                select(MaintenanceTicket)
                .options(
                    selectinload(MaintenanceTicket.employee),
                    selectinload(MaintenanceTicket.category),
                    selectinload(MaintenanceTicket.subcategory),
                    selectinload(MaintenanceTicket.issue_type),
                    selectinload(MaintenanceTicket.priority),
                    selectinload(MaintenanceTicket.location)
                )
                .where(
                    MaintenanceTicket.status_id == 1,
                    MaintenanceTicket.ticket_id.not_in(m_assigned_subq)
                )
                .order_by(MaintenanceTicket.created_at.asc())
            )
            m_res = await session.execute(m_stmt)
            unclaimed_maint = m_res.scalars().all()

        # 2. IT Domain Unclaimed Tickets
        if not admin.is_maintenance_admin or admin.is_master_admin:
            it_assigned_subq = select(TicketAssignment.ticket_id)
            it_stmt = (
                select(Ticket)
                .options(
                    selectinload(Ticket.employee),
                    selectinload(Ticket.category),
                    selectinload(Ticket.subcategory),
                    selectinload(Ticket.issue_type),
                    selectinload(Ticket.priority)
                )
                .where(
                    Ticket.status_id == 1,
                    Ticket.ticket_id.not_in(it_assigned_subq)
                )
                .order_by(Ticket.created_at.asc())
            )
            it_res = await session.execute(it_stmt)
            unclaimed_it = it_res.scalars().all()

        total_pending = len(unclaimed_maint) + len(unclaimed_it)
        if total_pending == 0:
            return

        header_notice = (
            f"📢 *UNCLAIMED PENDING TICKETS ({total_pending})*\n\n"
            f"Hello *{admin.full_name}*, the following open ticket(s) were raised while your 24-hour WhatsApp messaging window was closed.\n\n"
            f"Tap **[ 🔵 Claim Ticket ]** on any ticket below to claim it:"
        )
        await meta_api.send_text_message(sender_phone, header_notice)

        # Deliver Projects Unclaimed Tickets
        for t in unclaimed_maint:
            emp_name = t.employee.full_name if t.employee else "Staff Reporter"
            emp_phone = t.employee.phone if t.employee else ""
            cat_name = t.category.category_name if t.category else "Doors, Windows & Locks"
            sub_name = t.subcategory.subcategory_name if t.subcategory else "Door Latch & Hinges"
            issue_name = t.issue_type.issue_name if t.issue_type else "Custom Issue"
            priority_name = t.priority.priority_name if t.priority else "Medium"
            loc_name = t.location.location_name if t.location else "On-Site"
            room_area = t.room_area or "N/A"

            hazard_flag = "⚠️ URGENT SAFETY HAZARD | " if t.is_safety_hazard else ""
            header = f"🚨 NEW 🏗️ PROJECTS TICKET"
            body = (
                f"{hazard_flag}🎫 *Ticket ID:* `{t.ticket_number}`\n"
                f"👤 *Reporter:* {emp_name} (`+{emp_phone}`)\n"
                f"🏢 *Location:* {loc_name}\n"
                f"📍 *Room / Area:* {room_area}\n"
                f"📌 *Category:* {cat_name} ➡️ {sub_name}\n"
                f"⚙️ *Issue:* {issue_name}\n"
                f"🚨 *Priority:* {priority_name}\n"
                f"📝 *Description:* {t.description}"
            )
            footer = "Tap button below to claim ticket"
            buttons = [
                {"id": f"claim_{t.ticket_number}", "title": "🔵 Claim Ticket"}
            ]
            await meta_api.send_button_message(
                to_phone=sender_phone,
                body_text=body,
                buttons=buttons,
                header_text=header,
                footer_text=footer,
                image_id=t.image_id
            )
            await asyncio.sleep(0.5)

        # Deliver IT Support Unclaimed Tickets
        for t in unclaimed_it:
            emp_name = t.employee.full_name if t.employee else "Staff Reporter"
            emp_phone = t.employee.phone if t.employee else ""
            cat_name = t.category.category_name if t.category else "IT Equipment"
            sub_name = t.subcategory.subcategory_name if t.subcategory else "Computer & Laptop"
            issue_name = t.issue_type.issue_name if t.issue_type else "IT Issue"
            priority_name = t.priority.priority_name if t.priority else "Medium"

            header = f"🚨 NEW 💻 IT SUPPORT TICKET"
            body = (
                f"🎫 *Ticket ID:* `{t.ticket_number}`\n"
                f"👤 *Reporter:* {emp_name} (`+{emp_phone}`)\n"
                f"📌 *Category:* {cat_name} ➡️ {sub_name}\n"
                f"⚙️ *Issue:* {issue_name}\n"
                f"🚨 *Priority:* {priority_name}\n"
                f"📝 *Description:* {t.description}"
            )
            footer = "Tap button below to claim ticket"
            buttons = [
                {"id": f"claim_{t.ticket_number}", "title": "🔵 Claim Ticket"}
            ]
            await meta_api.send_button_message(
                to_phone=sender_phone,
                body_text=body,
                buttons=buttons,
                header_text=header,
                footer_text=footer,
                image_id=t.image_id
            )
            await asyncio.sleep(0.5)

    except Exception as e:
        logger.error(f"Error delivering pending unclaimed tickets to admin {sender_phone}: {e}", exc_info=True)


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

    # Match ACCEPT / CLAIM command: "accept TKT-...", "claim_TKT-...", "🔵 claim_TKT-...", "claim TKT-..."
    claim_match = re.match(r"^(?:🔵\s*)?(?:accept|claim)[_\s]+([A-Z0-9-]+)$", text_strip, re.IGNORECASE)
    # Match RESOLVE command: "resolve TKT-...", "resolve_TKT-...", "🟢 resolve_TKT-...", "resolve 1"
    resolve_match = re.match(r"^(?:🟢\s*)?resolve[_\s]+([A-Z0-9-]+)$", text_strip, re.IGNORECASE)

    # Check for bare button text: "🔵 Claim Ticket", "Claim Ticket", "claim", "accept"
    is_bare_claim = not claim_match and (text_lower in {"claim ticket", "claim", "accept", "accept ticket", "🔵 claim ticket"} or "claim ticket" in text_lower)
    is_bare_resolve = not resolve_match and (text_lower in {"resolve ticket", "resolve", "🟢 resolve ticket"} or "resolve ticket" in text_lower)

    raw_ticket_arg = None
    if is_bare_claim:
        if admin.is_maintenance_admin:
            m_assigned_subq = select(MaintenanceTicketAssignment.ticket_id)
            latest_open_stmt = (
                select(MaintenanceTicket)
                .where(MaintenanceTicket.status_id == 1, MaintenanceTicket.ticket_id.not_in(m_assigned_subq))
                .order_by(MaintenanceTicket.created_at.desc())
            )
            latest_t = (await session.execute(latest_open_stmt)).scalars().first()
            if latest_t:
                raw_ticket_arg = latest_t.ticket_number
                claim_match = True
        else:
            it_assigned_subq = select(TicketAssignment.ticket_id)
            latest_open_stmt = (
                select(Ticket)
                .where(Ticket.status_id == 1, Ticket.ticket_id.not_in(it_assigned_subq))
                .order_by(Ticket.created_at.desc())
            )
            latest_t = (await session.execute(latest_open_stmt)).scalars().first()
            if latest_t:
                raw_ticket_arg = latest_t.ticket_number
                claim_match = True

    elif is_bare_resolve:
        if admin.is_maintenance_admin:
            m_asg_stmt = (
                select(MaintenanceTicket)
                .join(MaintenanceTicketAssignment, MaintenanceTicket.ticket_id == MaintenanceTicketAssignment.ticket_id)
                .where(MaintenanceTicketAssignment.admin_id == admin.admin_id, MaintenanceTicket.status_id == 2)
                .order_by(MaintenanceTicket.updated_at.desc())
            )
            assigned_t = (await session.execute(m_asg_stmt)).scalars().first()
            if assigned_t:
                raw_ticket_arg = assigned_t.ticket_number
                resolve_match = True
        else:
            it_asg_stmt = (
                select(Ticket)
                .join(TicketAssignment, Ticket.ticket_id == TicketAssignment.ticket_id)
                .where(TicketAssignment.admin_id == admin.admin_id, Ticket.status_id == 2)
                .order_by(Ticket.updated_at.desc())
            )
            assigned_t = (await session.execute(it_asg_stmt)).scalars().first()
            if assigned_t:
                raw_ticket_arg = assigned_t.ticket_number
                resolve_match = True

    is_view_assigned = text_lower in {"cmd_my_assigned_tickets", "assigned", "my tickets", "view tickets", "my assigned tickets", "my assigned ticket"} or text_strip.startswith("cmd_my_assigned_tickets")
    is_summary = text_lower in {"cmd_admin_summary_report", "summary", "report", "summary report", "daily report"} or text_strip.startswith("cmd_admin_summary_report")
    is_raise_cmd = text_lower in {"cmd_raise_ticket", "raise ticket", "raise it ticket", "create ticket", "new ticket"} or text_strip.startswith("cmd_raise_ticket")
    raw_clean = re.sub(r"[^\w\s]", "", text_lower).strip()
    is_greeting = not is_view_assigned and not is_summary and not is_raise_cmd and not claim_match and not resolve_match and (
        raw_clean in {"hi", "hello", "menu", "admin", "start", "help", "hey"} or
        text_lower in {"hi", "hello", "menu", "admin", "start", "help", "hey", "/start", "/menu", "/admin", "/help"} or
        any(raw_clean.startswith(w) for w in ("hi", "hello", "hey", "menu", "admin", "start"))
    )

    state = await get_user_state(session, sender_phone)

    # If admin is in active ticket creation flow (raise_ticket) AND not sending a greeting, admin command, or reset:
    # Do NOT intercept description / text input as admin command! Let it flow to handle_flow!
    if not (is_greeting or is_view_assigned or is_summary or is_raise_cmd):
        if state and state.flow_name == "raise_ticket" and state.current_step in (
            "awaiting_description", "awaiting_room_area", "awaiting_other_location",
            "awaiting_category", "awaiting_subcategory", "awaiting_issue",
            "select_priority", "select_safety_hazard", "awaiting_image", "select_location", "select_domain"
        ):
            if not (claim_match or resolve_match or text_strip.startswith(("cmd_", "btn_", "claim_", "resolve_")) or text_lower in {"reset", "cancel"}):
                return False

    # Check if admin is currently answering resolution note prompt (ONLY IF NOT A BUTTON/COMMAND)
    if not claim_match and not resolve_match and not is_greeting and not is_view_assigned and not is_summary and not is_raise_cmd:
        if state and state.flow_name == "admin_resolution" and state.current_step == "awaiting_admin_resolution_note":
            return await handle_admin_resolution_note(session, admin, sender_phone, message_text, state)
        # If admin is NOT in active draft or resolution flow, treating any general message as Admin Dashboard Greeting!
        is_greeting = True

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

        # Deliver all unclaimed open tickets that were queued / missed during 24h window
        await deliver_pending_unclaimed_tickets_to_admin(session, admin, sender_phone)

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
        
        # Deliver all unclaimed open tickets that were queued / missed during 24h window
        await deliver_pending_unclaimed_tickets_to_admin(session, admin, sender_phone)

        tickets = []

        if admin.is_maintenance_admin or admin.is_master_admin:
            m_asg_stmt = (
                select(MaintenanceTicketAssignment)
                .options(
                    selectinload(MaintenanceTicketAssignment.ticket).selectinload(MaintenanceTicket.employee).selectinload(Employee.department),
                    selectinload(MaintenanceTicketAssignment.ticket).selectinload(MaintenanceTicket.employee).selectinload(Employee.location),
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
                    selectinload(TicketAssignment.ticket).selectinload(Ticket.employee).selectinload(Employee.department),
                    selectinload(TicketAssignment.ticket).selectinload(Ticket.employee).selectinload(Employee.location),
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

        # Sort tickets by created_at desc (newest first)
        tickets.sort(key=lambda t: t.created_at or datetime.datetime.min, reverse=True)

        summary_header = f"📋 *ACTIVE TICKETS ASSIGNED TO YOU ({len(tickets)} Active)*\n\nHello {admin.full_name},\nHere are all your pending support tickets:"
        await meta_api.send_text_message(sender_phone, summary_header)
        await asyncio.sleep(0.5)

        for t in tickets:
            try:
                emp = t.employee
                emp_name = emp.full_name if emp else "Staff Reporter"
                emp_phone = emp.phone if emp else ""
                dept_name = emp.department.department_name if emp and emp.department else ""
                loc_name = t.location.location_name if getattr(t, "location", None) and t.location else (emp.location.location_name if emp and emp.location else "")
                
                cat_name = t.category.category_name if t.category else "N/A"
                sub_name = t.subcategory.subcategory_name if t.subcategory else "N/A"
                issue_name = t.issue_type.issue_name if t.issue_type else "Custom Issue"
                p_name = t.priority.priority_name if t.priority else "Medium"
                status_str = STATUS_NAMES.get(t.status_id, "🟡 Open")

                is_maint_t = getattr(t, "domain", "") == "MAINTENANCE" or "TKT-MNT" in t.ticket_number
                domain_label = "🏗️ PROJECTS" if is_maint_t else "💻 IT"
                
                dept_str = f" ({dept_name})" if dept_name else ""
                loc_line = f"🏢 *Location:* {loc_name}\n" if loc_name else ""
                room_area_val = getattr(t, "room_area", None)
                if is_maint_t and room_area_val and room_area_val != "N/A":
                    loc_line += f"📍 *Room/Area:* {room_area_val}\n"

                hazard_info = "\n⚠️ *SAFETY HAZARD FLAG!*" if is_maint_t and getattr(t, "is_safety_hazard", False) else ""

                header = f"🎫 TICKET {t.ticket_number} ({domain_label})"
                body = (
                    f"👤 *Reporter:* {emp_name}{dept_str} (`+{emp_phone}`)\n"
                    f"{loc_line}"
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
                await asyncio.sleep(0.6)
            except Exception as e:
                logger.error(f"Error sending ticket card for {t.ticket_number}: {e}", exc_info=True)
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
        from app.handlers.flow_handler import start_ticket_creation_flow
        emp_record = (await session.execute(select(Employee).where(Employee.phone == sender_phone))).scalars().first()
        await start_ticket_creation_flow(session, sender_phone, emp_record)
        return True

    # 5. HANDLE RESOLVE BUTTON TAP OR COMMAND -> PROMPT FOR NOTES
    if not raw_ticket_arg:
        if hasattr(claim_match, "group"):
            raw_ticket_arg = claim_match.group(1).upper()
        elif hasattr(resolve_match, "group"):
            raw_ticket_arg = resolve_match.group(1).upper()

    if not raw_ticket_arg:
        return False

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

    # ----------------------------------------------------
    # HANDLE CLAIM COMMAND: [ ✋ Claim Ticket ] or "claim TKT-..."
    # ----------------------------------------------------
    if claim_match:
        if ticket.status_id in (3, 4):
            status_name = "Resolved" if ticket.status_id == 3 else "Closed"
            await meta_api.send_text_message(
                sender_phone,
                f"ℹ️ Ticket *{ticket.ticket_number}* is already marked as **{status_name}**."
            )
            return True

        # Check existing assignment
        if is_maint_ticket:
            asg_chk = select(MaintenanceTicketAssignment).options(selectinload(MaintenanceTicketAssignment.admin)).where(MaintenanceTicketAssignment.ticket_id == ticket.ticket_id)
            current_asg = (await session.execute(asg_chk)).scalars().first()
        else:
            asg_chk = select(TicketAssignment).options(selectinload(TicketAssignment.admin)).where(TicketAssignment.ticket_id == ticket.ticket_id)
            current_asg = (await session.execute(asg_chk)).scalars().first()

        # If already claimed by another admin
        if current_asg and current_asg.admin_id and current_asg.admin_id != admin.admin_id:
            already_admin_name = current_asg.admin.full_name if current_asg.admin else "another admin"
            await meta_api.send_text_message(
                sender_phone,
                f"ℹ️ *Ticket Already Claimed*\n\nTicket *{ticket.ticket_number}* was already claimed by *{already_admin_name}*."
            )
            return True

        # Pre-extract attributes before commit to avoid any DetachedInstance / MissingGreenlet errors
        ticket_id = ticket.ticket_id
        ticket_num = ticket.ticket_number
        ticket_desc = ticket.description
        ticket_image_id = ticket.image_id if (ticket.image_id and len(ticket.image_id) > 5 and ticket.image_id.lower() != "none") else None
        cat_name = ticket.category.category_name if ticket.category else "N/A"
        sub_name = ticket.subcategory.subcategory_name if ticket.subcategory else "N/A"
        issue_name = ticket.issue_type.issue_name if ticket.issue_type else "Custom Issue"
        emp_name = ticket.employee.full_name if ticket.employee else "Staff Reporter"
        emp_phone = ticket.employee.phone if ticket.employee and ticket.employee.phone else ""

        # Assign ticket to this claiming admin
        if not current_asg:
            if is_maint_ticket:
                session.add(MaintenanceTicketAssignment(ticket_id=ticket_id, admin_id=admin.admin_id))
            else:
                session.add(TicketAssignment(ticket_id=ticket_id, admin_id=admin.admin_id))
        else:
            current_asg.admin_id = admin.admin_id

        # Update status to In Progress
        ticket.status_id = 2 # In Progress
        ticket.updated_at = datetime.datetime.utcnow()
        await session.commit()

        # 1. Confirm to claiming admin with interactive Resolve button
        claim_confirm_msg = (
            f"✅ *TICKET CLAIMED SUCCESSFULLY!*\n\n"
            f"🎫 *Ticket ID:* `{ticket_num}`\n"
            f"👤 *Reporter:* {emp_name} (`+{emp_phone}`)\n"
            f"📌 *Category:* {cat_name} ➡️ {sub_name}\n"
            f"⚙️ *Issue:* {issue_name}\n"
            f"📝 *Description:* {ticket_desc}\n\n"
            f"You are now the assigned support admin for this ticket. Tap below when completed:"
        )
        resolve_btns = [
            {"id": f"resolve_{ticket_num}", "title": "🟢 Resolve Ticket"}
        ]
        try:
            await meta_api.send_button_message(
                to_phone=sender_phone,
                body_text=claim_confirm_msg,
                buttons=resolve_btns,
                header_text="✅ TICKET ASSIGNED TO YOU",
                footer_text="Tap button to resolve when done",
                image_id=ticket_image_id
            )
        except Exception as send_err:
            logger.error(f"Error sending button confirmation: {send_err}", exc_info=True)
            await meta_api.send_text_message(sender_phone, claim_confirm_msg)

        # 2. Notify co-admins in the same domain
        try:
            if is_maint_ticket:
                co_stmt = select(SupportAdmin).where(SupportAdmin.is_maintenance_admin == True, SupportAdmin.active == True)
            else:
                co_stmt = select(SupportAdmin).where(SupportAdmin.active == True, SupportAdmin.is_maintenance_admin == False)

            co_admins = (await session.execute(co_stmt)).scalars().all()
            for ca in co_admins:
                if ca.phone != sender_phone and ca.phone != settings.master_admin_phone:
                    co_notice = (
                        f"ℹ️ *TICKET CLAIMED UPDATE*\n\n"
                        f"Ticket *{ticket_num}* ({cat_name} ➡️ {sub_name}) has been claimed by *{admin.full_name}*."
                    )
                    await meta_api.send_text_message(ca.phone, co_notice)
        except Exception as co_err:
            logger.error(f"Error notifying co-admins of claim: {co_err}")

        # 3. Notify Master Admin Fazal
        try:
            if settings.master_admin_phone and sender_phone != settings.master_admin_phone:
                master_claim_msg = (
                    f"ℹ️ *[MASTER ALERT] TICKET CLAIMED*\n\n"
                    f"🎫 *Ticket ID:* `{ticket_num}`\n"
                    f"👤 *Reporter:* {emp_name} (`+{emp_phone}`)\n"
                    f"👤 *Claimed By Admin:* {admin.full_name} (`+{admin.phone}`)\n"
                    f"📊 *Status:* 🔵 IN PROGRESS"
                )
                await meta_api.send_text_message(settings.master_admin_phone, master_claim_msg)
        except Exception as master_err:
            logger.error(f"Error notifying master admin of claim: {master_err}")

        # 4. Notify Reporter / Employee
        try:
            domain_title = "Building Projects" if is_maint_ticket else "IT Support"
            if emp_phone:
                emp_update = (
                    f"👨‍💻 *{domain_title} Support Update*\n\n"
                    f"Your support ticket *{ticket_num}* has been claimed by Support Admin *{admin.full_name}* and is now **IN PROGRESS**."
                )
                await meta_api.send_text_message(emp_phone, emp_update)
        except Exception as emp_err:
            logger.error(f"Error notifying reporter of claim: {emp_err}")

        return True

    # ----------------------------------------------------
    # HANDLE RESOLVE COMMAND: [ 🟢 Resolve Ticket ] or "resolve TKT-..."
    # ----------------------------------------------------
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
