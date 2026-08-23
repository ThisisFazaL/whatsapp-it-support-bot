import datetime
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Ticket, MaintenanceTicket, Employee
from app.meta_api import meta_api

MY_TICKETS_KEYWORDS = {"my tickets", "my status", "status", "tickets", "my ticket"}

STATUS_ICONS = {
    1: "🟡 Open",
    2: "🔵 In Progress",
    3: "🟢 Resolved",
    4: "⚪ Closed"
}

async def handle_my_tickets(session: AsyncSession, employee: Employee, message_text: str) -> bool:
    """
    Checks if message is a request to view employee's tickets across IT and Maintenance tables.
    Returns True if handled, False otherwise.
    """
    text_clean = message_text.strip().lower()
    if text_clean not in MY_TICKETS_KEYWORDS:
        return False

    # Fetch IT Tickets
    it_stmt = (
        select(Ticket)
        .options(
            selectinload(Ticket.category),
            selectinload(Ticket.subcategory),
            selectinload(Ticket.issue_type),
            selectinload(Ticket.priority),
            selectinload(Ticket.status)
        )
        .where(Ticket.employee_id == employee.employee_id)
        .order_by(Ticket.ticket_id.desc())
        .limit(10)
    )
    it_res = await session.execute(it_stmt)
    it_tickets = it_res.scalars().all()

    # Fetch Maintenance Tickets
    maint_stmt = (
        select(MaintenanceTicket)
        .options(
            selectinload(MaintenanceTicket.category),
            selectinload(MaintenanceTicket.subcategory),
            selectinload(MaintenanceTicket.issue_type),
            selectinload(MaintenanceTicket.priority),
            selectinload(MaintenanceTicket.status)
        )
        .where(MaintenanceTicket.employee_id == employee.employee_id)
        .order_by(MaintenanceTicket.ticket_id.desc())
        .limit(10)
    )
    maint_res = await session.execute(maint_stmt)
    maint_tickets = maint_res.scalars().all()

    all_tickets = list(it_tickets) + list(maint_tickets)
    all_tickets.sort(key=lambda t: t.created_at or datetime.datetime.min, reverse=True)

    if not all_tickets:
        await meta_api.send_text_message(
            employee.phone,
            f"📋 *Your Support Tickets*\n\nYou currently have no support tickets logged.\n\nReply *'menu'* to raise a new ticket!"
        )
        return True

    ticket_blocks = []
    for idx, t in enumerate(all_tickets[:10], start=1):
        cat_name = t.category.category_name if t.category else "General"
        sub_name = t.subcategory.subcategory_name if t.subcategory else ""
        issue_name = t.issue_type.issue_name if t.issue_type else "Custom Issue"
        p_name = t.priority.priority_name if t.priority else "Medium"
        status_str = STATUS_ICONS.get(t.status_id, "🟡 Open")
        created_str = t.created_at.strftime("%d %b %Y, %H:%M") if t.created_at else ""
        domain_label = "🏗️ Projects" if getattr(t, "domain", "") == "MAINTENANCE" or "TKT-MNT" in t.ticket_number else "💻 IT"
        room_str = f" ({t.room_area})" if getattr(t, "room_area", None) else ""
        img_str = " 🖼️ *(Photo attached)*" if t.image_id else ""

        block = (
            f"{idx}. 🎫 *{t.ticket_number}* ({domain_label}){img_str}\n"
            f"   📌 {cat_name}" + (f" ➡️ {sub_name}" if sub_name else "") + f"{room_str}\n"
            f"   ⚙️ {issue_name}\n"
            f"   🚨 Priority: *{p_name}* | Status: *{status_str}*\n"
            f"   📅 Date: _{created_str}_"
        )
        ticket_blocks.append(block)

    tickets_msg = "\n\n".join(ticket_blocks)
    full_msg = (
        f"📋 *Your Support Tickets ({employee.full_name})*\n\n"
        f"{tickets_msg}\n\n"
        f"💡 _Reply 'menu' to raise a new ticket._"
    )

    await meta_api.send_text_message(employee.phone, full_msg)
    return True
