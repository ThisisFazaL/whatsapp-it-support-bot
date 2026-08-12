import datetime
import logging
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Ticket, SupportAdmin, Category, Priority, TicketStatus
from app.meta_api import meta_api

logger = logging.getLogger("reports")

async def get_master_admins(session: AsyncSession):
    """Returns all active master support admins."""
    stmt = select(SupportAdmin).where(SupportAdmin.is_master_admin == True, SupportAdmin.active == True)
    res = await session.execute(stmt)
    return res.scalars().all()

async def generate_daily_report_text(session: AsyncSession) -> str:
    """Generates formatted daily ticket metrics report text."""
    now = datetime.datetime.utcnow()
    today_start = datetime.datetime(now.year, now.month, now.day, 0, 0, 0)
    today_str = now.strftime("%d %B %Y")

    # Today's tickets count
    stmt_today = select(func.count(Ticket.ticket_id)).where(Ticket.created_at >= today_start)
    today_count = (await session.execute(stmt_today)).scalar() or 0

    # Total open / in progress / resolved / closed
    stmt_open = select(func.count(Ticket.ticket_id)).where(Ticket.status_id == 1)
    open_count = (await session.execute(stmt_open)).scalar() or 0

    stmt_in_prog = select(func.count(Ticket.ticket_id)).where(Ticket.status_id == 2)
    in_prog_count = (await session.execute(stmt_in_prog)).scalar() or 0

    stmt_resolved = select(func.count(Ticket.ticket_id)).where(Ticket.status_id == 3, Ticket.updated_at >= today_start)
    resolved_today = (await session.execute(stmt_resolved)).scalar() or 0

    stmt_closed = select(func.count(Ticket.ticket_id)).where(Ticket.status_id == 4, Ticket.closed_at >= today_start)
    closed_today = (await session.execute(stmt_closed)).scalar() or 0

    report = (
        f"📊 *DAILY IT SUPPORT TICKET REPORT*\n"
        f"📅 *Date:* {today_str}\n\n"
        f"📈 *Today's Metrics:*\n"
        f"• New Tickets Today: *{today_count}*\n"
        f"• Resolved Today: *{resolved_today}*\n"
        f"• Closed Today: *{closed_today}*\n\n"
        f"📋 *Current System Overview:*\n"
        f"• 🟡 Open Tickets: *{open_count}*\n"
        f"• 🔵 In Progress: *{in_prog_count}*\n\n"
        f"💡 _Master Summary Report generated automatically._"
    )
    return report

async def generate_monthly_report_text(session: AsyncSession) -> str:
    """Generates formatted monthly ticket metrics report text."""
    now = datetime.datetime.utcnow()
    month_start = datetime.datetime(now.year, now.month, 1, 0, 0, 0)
    month_str = now.strftime("%B %Y")

    stmt_month = select(func.count(Ticket.ticket_id)).where(Ticket.created_at >= month_start)
    month_count = (await session.execute(stmt_month)).scalar() or 0

    stmt_closed = select(func.count(Ticket.ticket_id)).where(Ticket.status_id == 4, Ticket.closed_at >= month_start)
    closed_month = (await session.execute(stmt_closed)).scalar() or 0

    report = (
        f"📈 *MONTHLY IT SUPPORT METRICS REPORT*\n"
        f"🗓️ *Month:* {month_str}\n\n"
        f"📊 *Monthly Performance:*\n"
        f"• Total Tickets Created: *{month_count}*\n"
        f"• Total Tickets Closed: *{closed_month}*\n"
        f"• Closure Rate: *{((closed_month / month_count)*100):.1f}%* " if month_count > 0 else "• Closure Rate: *N/A*\n"
        f"\n💡 _Master Executive Monthly Summary._"
    )
    return report

async def send_daily_report_to_master(session: AsyncSession):
    """Sends daily report to master admins."""
    masters = await get_master_admins(session)
    if not masters:
        return
    text = await generate_daily_report_text(session)
    for m in masters:
        await meta_api.send_text_message(m.phone, text)

async def send_monthly_report_to_master(session: AsyncSession):
    """Sends monthly report to master admins."""
    masters = await get_master_admins(session)
    if not masters:
        return
    text = await generate_monthly_report_text(session)
    for m in masters:
        await meta_api.send_text_message(m.phone, text)

if __name__ == "__main__":
    import asyncio
    from app.database import async_session_factory
    async def cli():
        async with async_session_factory() as s:
            print(await generate_daily_report_text(s))
            print(await generate_monthly_report_text(s))
    asyncio.run(cli())
