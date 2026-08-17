import datetime
import logging
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Ticket, TicketAssignment, SupportAdmin, Category, Subcategory, IssueType, Priority, TicketStatus, Employee
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

async def generate_daily_master_report_text(session: AsyncSession) -> str:
    """
    Generates itemized daily master report text for 8:00 PM IST.
    Lists each and every ticket logged on that day grouped by Support Admin.
    """
    now = datetime.datetime.utcnow()
    today_start = datetime.datetime(now.year, now.month, now.day, 0, 0, 0)
    today_str = now.strftime("%d %B %Y")

    stmt = (
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
    res = await session.execute(stmt)
    today_tickets = res.scalars().all()

    total_count = len(today_tickets)
    open_count = sum(1 for t in today_tickets if t.status_id == 1)
    in_prog_count = sum(1 for t in today_tickets if t.status_id == 2)
    resolved_count = sum(1 for t in today_tickets if t.status_id in (3, 4))

    header = (
        f"📊 *DAILY IT SUPPORT MASTER REPORT*\n"
        f"📅 *Date:* {today_str}\n\n"
        f"📈 *Summary Overview:*\n"
        f"• Total Tickets Today: *{total_count}*\n"
        f"• 🟡 Open: *{open_count}* | 🔵 In Progress: *{in_prog_count}* | 🟢 Fixed/Closed: *{resolved_count}*\n"
        f"------------------------------------\n"
    )

    if not today_tickets:
        return header + "\n✨ *No tickets logged today! Everything is running smoothly.*"

    t_ids = [t.ticket_id for t in today_tickets]
    asg_stmt = (
        select(TicketAssignment)
        .options(selectinload(TicketAssignment.admin))
        .where(TicketAssignment.ticket_id.in_(t_ids))
    )
    asg_res = await session.execute(asg_stmt)
    assignments = asg_res.scalars().all()
    asg_map = {a.ticket_id: a.admin for a in assignments}

    admin_groups = {}
    for t in today_tickets:
        admin = asg_map.get(t.ticket_id)
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

            line = (
                f"• 🎫 *{t.ticket_number}* | Status: *{status_str}* | Priority: *{p_name}*\n"
                f"  👤 {emp_name} ({dept_name})\n"
                f"  📌 {cat_name} ➡️ {sub_name}\n"
                f"  ⚙️ {issue_name}\n"
                f"  📝 _{desc}_"
            )
            t_lines.append(line)

        sections.append(sec_header + "\n" + "\n".join(t_lines))

    report_body = "\n\n".join(sections)
    footer = "\n\n💡 _Automated Daily Master Executive Report delivered at 8:00 PM IST._"
    
    return header + report_body + footer

async def send_daily_report_to_master(session: AsyncSession):
    """
    Delivers both text summary and PDF Document Executive Report
    directly to Master Admin (Fazal - 919265368695) every day at 8:00 PM IST.
    """
    master_phone = settings.master_admin_phone or "919265368695"
    logger.info(f"Generating and sending 8:00 PM IST Daily Master Report to Master Admin ({master_phone})...")

    # 1. Send Text Report Summary
    text_summary = await generate_daily_master_report_text(session)
    await meta_api.send_text_message(master_phone, text_summary)

    # 2. Generate PDF Report Document
    now_str = datetime.datetime.now().strftime("%d%b%Y")
    pdf_filename = f"Daily_IT_Support_Master_Report_{now_str}.pdf"
    try:
        create_daily_report_pdf(pdf_filename)
        pdf_url = f"https://github.com/ThisisFazaL/whatsapp-it-support-bot/raw/main/Daily_IT_Support_Master_Report_Sample.pdf"

        # 3. Send PDF Document Attachment via WhatsApp
        await meta_api.send_document_message(
            to_phone=master_phone,
            document_url=pdf_url,
            filename=pdf_filename,
            caption=f"📄 *DAILY IT SUPPORT EXECUTIVE REPORT (PDF)*\n📅 Date: {datetime.datetime.now().strftime('%d %B %Y')}"
        )
        logger.info("PDF Executive Report sent to Master Admin via WhatsApp!")

    except Exception as e:
        logger.error(f"Failed to generate/send PDF report: {e}", exc_info=True)

if __name__ == "__main__":
    import asyncio
    from app.database import async_session_factory
    async def cli():
        async with async_session_factory() as s:
            await send_daily_report_to_master(s)
    asyncio.run(cli())
