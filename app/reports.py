import datetime
import logging
import os
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import (
    Ticket, MaintenanceTicket, TicketAssignment, MaintenanceTicketAssignment,
    SupportAdmin, Category, Subcategory, IssueType, Priority, TicketStatus, Employee
)
from app.config import settings
from app.meta_api import meta_api
from generate_daily_report_pdf import create_daily_report_pdf

logger = logging.getLogger("reports")

STATUS_ICONS = {
    1: "🟡 Open",
    2: "🔵 In Progress",
    3: "🟢 Resolved",
    4: "⚪ Closed"
}

async def get_master_admins(session: AsyncSession):
    """Returns all active master support admins."""
    stmt = select(SupportAdmin).where(SupportAdmin.is_master_admin == True, SupportAdmin.active == True)
    res = await session.execute(stmt)
    return res.scalars().all()

async def generate_daily_master_report_data(session: AsyncSession):
    """
    Generates itemized daily master report text and returns (text_summary, today_tickets, asg_map).
    Lists each and every ticket logged on that day across IT (tickets) and Maintenance (maintenance_tickets) tables.
    """
    now = datetime.datetime.utcnow()
    today_start = datetime.datetime(now.year, now.month, now.day, 0, 0, 0)
    today_str = now.strftime("%d %B %Y")

    # 1. Fetch IT Tickets created today
    it_stmt = (
        select(Ticket)
        .options(
            selectinload(Ticket.employee).selectinload(Employee.department),
            selectinload(Ticket.category),
            selectinload(Ticket.subcategory),
            selectinload(Ticket.issue_type),
            selectinload(Ticket.priority),
            selectinload(Ticket.status)
        )
        .where(Ticket.created_at >= today_start)
        .order_by(Ticket.ticket_id.asc())
    )
    it_res = await session.execute(it_stmt)
    it_tickets = it_res.scalars().all()

    # 2. Fetch Maintenance Tickets created today
    maint_stmt = (
        select(MaintenanceTicket)
        .options(
            selectinload(MaintenanceTicket.employee).selectinload(Employee.department),
            selectinload(MaintenanceTicket.category),
            selectinload(MaintenanceTicket.subcategory),
            selectinload(MaintenanceTicket.issue_type),
            selectinload(MaintenanceTicket.priority),
            selectinload(MaintenanceTicket.status)
        )
        .where(MaintenanceTicket.created_at >= today_start)
        .order_by(MaintenanceTicket.ticket_id.asc())
    )
    maint_res = await session.execute(maint_stmt)
    maint_tickets = maint_res.scalars().all()

    today_tickets = list(it_tickets) + list(maint_tickets)
    today_tickets.sort(key=lambda t: t.created_at or datetime.datetime.min)

    total_count = len(today_tickets)
    it_count = len(it_tickets)
    maint_count = len(maint_tickets)
    open_count = sum(1 for t in today_tickets if t.status_id == 1)
    in_prog_count = sum(1 for t in today_tickets if t.status_id == 2)
    resolved_count = sum(1 for t in today_tickets if t.status_id in (3, 4))
    hazard_count = sum(1 for t in today_tickets if getattr(t, "is_safety_hazard", False))

    header = (
        f"📊 *DAILY MASTER EXECUTIVE SUPPORT REPORT*\n"
        f"📅 *Date:* {today_str}\n\n"
        f"📈 *Summary Overview:*\n"
        f"• Total Tasks Today: *{total_count}* (💻 IT: *{it_count}* | 🛠️ Maintenance: *{maint_count}*)\n"
        f"• 🟡 Open: *{open_count}* | 🔵 In Progress: *{in_prog_count}* | 🟢 Fixed/Closed: *{resolved_count}*\n"
        f"• ⚠️ Urgent Safety Hazards: *{hazard_count}*\n"
        f"------------------------------------\n"
    )

    asg_map = {}
    it_ids = [t.ticket_id for t in it_tickets]
    if it_ids:
        asg_stmt = (
            select(TicketAssignment)
            .options(selectinload(TicketAssignment.admin))
            .where(TicketAssignment.ticket_id.in_(it_ids))
        )
        asg_res = await session.execute(asg_stmt)
        for a in asg_res.scalars().all():
            asg_map[f"IT_{a.ticket_id}"] = a.admin

    maint_ids = [t.ticket_id for t in maint_tickets]
    if maint_ids:
        m_asg_stmt = (
            select(MaintenanceTicketAssignment)
            .options(selectinload(MaintenanceTicketAssignment.admin))
            .where(MaintenanceTicketAssignment.ticket_id.in_(maint_ids))
        )
        m_asg_res = await session.execute(m_asg_stmt)
        for a in m_asg_res.scalars().all():
            asg_map[f"MAINT_{a.ticket_id}"] = a.admin

    if not today_tickets:
        return header + "\n✨ *No tickets logged today! Everything is running smoothly.*", today_tickets, asg_map

    admin_groups = {}
    for t in today_tickets:
        is_m = getattr(t, "domain", "") == "MAINTENANCE" or "TKT-MNT" in t.ticket_number
        key = f"MAINT_{t.ticket_id}" if is_m else f"IT_{t.ticket_id}"
        admin = asg_map.get(key)
        admin_key = admin.full_name if admin else "Unassigned"
        admin_phone = f" (+{admin.phone})" if admin else ""
        full_admin_title = f"{admin_key}{admin_phone}"

        if full_admin_title not in admin_groups:
            admin_groups[full_admin_title] = []
        admin_groups[full_admin_title].append(t)

    sections = []
    for admin_title, t_list in admin_groups.items():
        sec_header = f"👤 *ADMIN: {admin_title}* ({len(t_list)} tickets)"
        t_lines = []
        for t in t_list:
            emp_name = t.employee.full_name if t.employee else "Unknown"
            dept_name = t.employee.department.department_name if t.employee and t.employee.department else "General"
            cat_name = t.category.category_name if t.category else ""
            sub_name = t.subcategory.subcategory_name if t.subcategory else ""
            issue_name = t.issue_type.issue_name if t.issue_type else "Custom Issue"
            status_str = STATUS_ICONS.get(t.status_id, "🟡 Open")
            p_name = t.priority.priority_name if t.priority else "Medium"
            desc = t.description[:60] + "..." if len(t.description) > 60 else t.description
            domain_label = "🛠️ Maint" if getattr(t, "domain", "") == "MAINTENANCE" or "TKT-MNT" in t.ticket_number else "💻 IT"
            room_str = f" | 📍 {t.room_area}" if getattr(t, "room_area", None) else ""
            hazard_str = " | ⚠️ HAZARD" if getattr(t, "is_safety_hazard", False) else ""
            res_note_str = f"\n  🔧 _Resolution Note: {t.resolution_note}_" if getattr(t, "resolution_note", None) else ""

            line = (
                f"• 🎫 *{t.ticket_number}* ({domain_label}) | Status: *{status_str}* | Priority: *{p_name}*{hazard_str}\n"
                f"  👤 {emp_name} ({dept_name}){room_str}\n"
                f"  📌 {cat_name} ➡️ {sub_name}\n"
                f"  ⚙️ {issue_name}\n"
                f"  📝 _{desc}_{res_note_str}"
            )
            t_lines.append(line)

        sections.append(sec_header + "\n" + "\n".join(t_lines))

    report_body = "\n\n".join(sections)
    footer = "\n\n💡 _Automated Daily Master Executive Report delivered at 5:00 PM / EOD._"
    
    text_summary = header + report_body + footer
    return text_summary, today_tickets, asg_map

async def send_daily_report_to_master(session: AsyncSession):
    """
    Delivers both text summary and PDF Document Executive Report
    directly to Master Admin (Fazal - 919265368695) daily.
    """
    master_phone = settings.master_admin_phone or "919265368695"
    logger.info(f"Generating and sending Daily Master Report to Master Admin ({master_phone})...")

    # 1. Fetch live tickets and generate Text Report Summary
    text_summary, today_tickets, asg_map = await generate_daily_master_report_data(session)
    await meta_api.send_text_message(master_phone, text_summary)

    # 2. Generate Dynamic PDF Report Document built 100% from Live Database Tickets
    now_str = datetime.datetime.now().strftime("%d%b%Y")
    pdf_filename = f"Daily_IT_Facilities_Master_Report_{now_str}.pdf"
    local_path = "Daily_IT_Support_Master_Report_Sample.pdf"
    try:
        create_daily_report_pdf(local_path, today_tickets=today_tickets, asg_map=asg_map)
        pdf_url = "https://whatsapp-it-support-bot.onrender.com/daily-report.pdf"

        # 3. Send PDF Document Attachment via WhatsApp Meta Cloud API (Media ID Upload + Direct URL Fallback)
        res_doc = await meta_api.send_document_message(
            to_phone=master_phone,
            document_url=pdf_url,
            filename=pdf_filename,
            caption=f"📄 *DAILY IT & FACILITIES EXECUTIVE REPORT (PDF)*\n📅 Date: {datetime.datetime.now().strftime('%d %B %Y')}",
            local_file_path=local_path
        )
        logger.info(f"PDF Executive Report sent to Master Admin via WhatsApp! Result: {res_doc}")

    except Exception as e:
        logger.error(f"Failed to generate/send PDF report: {e}", exc_info=True)

if __name__ == "__main__":
    import asyncio
    from app.database import async_session_factory
    async def cli():
        async with async_session_factory() as s:
            await send_daily_report_to_master(s)
    asyncio.run(cli())
