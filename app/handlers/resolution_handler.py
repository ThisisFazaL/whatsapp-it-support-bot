import datetime
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import Ticket, MaintenanceTicket, TicketAssignment, MaintenanceTicketAssignment, SupportAdmin
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
    Handles both IT tickets (Ticket table) and Building Maintenance tickets (MaintenanceTicket table).
    Returns True when processed.
    """
    ticket_id = current_data.get("ticket_id")
    ticket_number = current_data.get("ticket_number", "")
    is_maint = current_data.get("is_maint", False) or "TKT-MNT" in ticket_number

    if not ticket_id:
        await clear_user_state(session, sender_phone)
        await meta_api.send_text_message(sender_phone, "Ticket context missing. State reset.")
        return True

    # Retrieve ticket details from appropriate table
    if is_maint:
        stmt = (
            select(MaintenanceTicket)
            .options(
                selectinload(MaintenanceTicket.employee),
                selectinload(MaintenanceTicket.category),
                selectinload(MaintenanceTicket.subcategory),
                selectinload(MaintenanceTicket.issue_type),
                selectinload(MaintenanceTicket.priority)
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
                selectinload(Ticket.issue_type),
                selectinload(Ticket.priority)
            )
            .where(Ticket.ticket_id == ticket_id)
        )

    res = await session.execute(stmt)
    ticket = res.scalars().first()

    if not ticket:
        await clear_user_state(session, sender_phone)
        await meta_api.send_text_message(sender_phone, "Ticket no longer exists. State reset.")
        return True

    choice = message_text.strip().lower()

    # Load ticket context details
    cat_name = ticket.category.category_name if ticket.category else "N/A"
    sub_name = ticket.subcategory.subcategory_name if ticket.subcategory else "N/A"
    issue_name = ticket.issue_type.issue_name if ticket.issue_type else "Custom Issue"
    emp_name = ticket.employee.full_name if ticket.employee else "N/A"
    emp_phone = f" (+{ticket.employee.phone})" if ticket.employee else ""
    domain_label = "Building Maintenance" if is_maint else "IT Support"

    # Fetch assigned admin
    if is_maint:
        assign_stmt = (
            select(MaintenanceTicketAssignment)
            .options(selectinload(MaintenanceTicketAssignment.admin))
            .where(MaintenanceTicketAssignment.ticket_id == ticket.ticket_id)
        )
    else:
        assign_stmt = (
            select(TicketAssignment)
            .options(selectinload(TicketAssignment.admin))
            .where(TicketAssignment.ticket_id == ticket.ticket_id)
        )

    assign_res = await session.execute(assign_stmt)
    assignment = assign_res.scalars().first()
    admin_name = assignment.admin.full_name if assignment and assignment.admin else "Support Team"
    admin_phone = f" (+{assignment.admin.phone})" if assignment and assignment.admin else ""

    t_num = ticket.ticket_number

    if choice in ("1", "confirm_close_ticket", "confirm & close", "✅ confirm & close", "close", "confirm") or choice.startswith("confirm_close") or choice.startswith("confirm_resolve_"):
        # 1 = Close Ticket (status_id = 4)
        ticket.status_id = 4
        ticket.closed_at = datetime.datetime.utcnow()
        ticket.updated_at = datetime.datetime.utcnow()
        await session.commit()
        await clear_user_state(session, sender_phone)

        # Notify Employee
        await meta_api.send_text_message(
            sender_phone,
            f"🎉 *{domain_label} Ticket Closed*\n\nThank you for confirming! Ticket *{t_num}* is now officially **CLOSED**."
        )

        # Notify Assigned Admin
        if assignment and assignment.admin:
            await meta_api.send_text_message(
                assignment.admin.phone,
                f"ℹ️ *Ticket Resolution Confirmed*\n\n"
                f"Employee {emp_name} confirmed resolution for {domain_label} Ticket *{t_num}*. Ticket is now CLOSED."
            )

        # Notify Master Admin Fazal
        if settings.master_admin_phone:
            master_closed = (
                f"🎉 *[MASTER ALERT] TICKET OFFICIALLY CLOSED* ⚪\n\n"
                f"🎫 *Ticket ID:* `{t_num}` ({domain_label})\n"
                f"👤 *Employee:* {emp_name}{emp_phone}\n"
                f"📌 *Category:* {cat_name} ➡️ {sub_name}\n"
                f"⚙️ *Issue:* {issue_name}\n"
                f"📝 *Description:* {ticket.description}\n\n"
                f"👤 *Resolved By:* {admin_name}{admin_phone}\n"
                f"📊 *Status:* ⚪ CLOSED (Confirmed by Employee)"
            )
            await meta_api.send_text_message(settings.master_admin_phone, master_closed)

        # Notify Executive Observers of Ticket Closed
        observer_closed = (
            f"🎉 *[EXECUTIVE OBSERVER ALERT] TICKET OFFICIALLY CLOSED*\n\n"
            f"🎫 *Ticket ID:* `{t_num}` ({domain_label})\n"
            f"👤 *Employee:* {emp_name}{emp_phone}\n"
            f"📌 *Category:* {cat_name} ➡️ {sub_name}\n"
            f"⚙️ *Issue:* {issue_name}\n"
            f"👤 *Resolved By:* {admin_name}{admin_phone}\n"
            f"📊 *Status:* ⚪ CLOSED (Confirmed by Employee)"
        )

        for obs_phone in settings.executive_observer_phones:
            if obs_phone != settings.master_admin_phone:
                await meta_api.send_text_message(obs_phone, observer_closed)

        return True

    elif choice in ("2", "reopen_ticket", "reopen ticket", "🔄 reopen ticket", "reopen", "cancel") or choice.startswith("reopen_"):
        # 2 = Reopen Ticket (status_id = 1)
        ticket.status_id = 1
        ticket.updated_at = datetime.datetime.utcnow()
        await session.commit()
        await clear_user_state(session, sender_phone)

        # Notify Employee
        await meta_api.send_text_message(
            sender_phone,
            f"🔄 *{domain_label} Ticket Reopened*\n\nTicket *{t_num}* has been **REOPENED**. Our Support team has been notified and will assist you."
        )

        # Notify Assigned Admin
        if assignment and assignment.admin:
            await meta_api.send_text_message(
                assignment.admin.phone,
                f"🚨 *Ticket Reopened*\n\n"
                f"Employee {emp_name} requested to REOPEN {domain_label} Ticket *{t_num}*. Status changed back to **OPEN**."
            )

        # Notify Master Admin Fazal
        if settings.master_admin_phone:
            master_reopened = (
                f"🚨 *[MASTER ALERT] TICKET REOPENED* 🔄\n\n"
                f"🎫 *Ticket ID:* `{t_num}` ({domain_label})\n"
                f"👤 *Employee:* {emp_name}{emp_phone}\n"
                f"📌 *Category:* {cat_name} ➡️ {sub_name}\n"
                f"⚙️ *Issue:* {issue_name}\n"
                f"📝 *Description:* {ticket.description}\n\n"
                f"👤 *Assigned Admin:* {admin_name}{admin_phone}\n"
                f"📊 *Status:* 🟡 REOPENED (Needs Attention)"
            )
            await meta_api.send_text_message(settings.master_admin_phone, master_reopened)

        # Notify Executive Observers
        observer_reopened = (
            f"🚨 *[EXECUTIVE OBSERVER ALERT] TICKET REOPENED*\n\n"
            f"🎫 *Ticket ID:* `{t_num}` ({domain_label})\n"
            f"👤 *Employee:* {emp_name}{emp_phone}\n"
            f"📌 *Category:* {cat_name} ➡️ {sub_name}\n"
            f"⚙️ *Issue:* {issue_name}\n"
            f"👤 *Assigned Admin:* {admin_name}{admin_phone}\n"
            f"📊 *Status:* 🟡 REOPENED (Needs Attention)"
        )
        for obs_phone in settings.executive_observer_phones:
            if obs_phone != settings.master_admin_phone:
                await meta_api.send_text_message(obs_phone, observer_reopened)

        return True

    else:
        # Invalid option
        await meta_api.send_text_message(
            sender_phone,
            f"❓ *Invalid Selection*\n\nPlease reply with:\n1️⃣ *1* to Confirm & Close Ticket\n2️⃣ *2* to Reopen Ticket"
        )
        return True
