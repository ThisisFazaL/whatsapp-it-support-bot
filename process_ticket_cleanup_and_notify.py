import asyncio
import logging
from sqlalchemy import select, delete, text
from sqlalchemy.orm import selectinload
from app.database import (
    async_session_factory, MaintenanceTicket, MaintenanceTicketAssignment,
    SupportAdmin, Employee, Category, Subcategory, IssueType, Priority, engine
)
from app.meta_api import meta_api
from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("reset_maint")

async def reset_and_create_ticket_1():
    logger.info("Executing complete reset of maintenance tickets and creating Ticket #1...")
    async with async_session_factory() as session:
        # 1. Delete all existing maintenance ticket assignments and maintenance tickets
        await session.execute(delete(MaintenanceTicketAssignment))
        await session.execute(delete(MaintenanceTicket))
        await session.commit()

        # Reset PostgreSQL sequence if running on Postgres
        try:
            await session.execute(text("ALTER SEQUENCE maintenance_tickets_ticket_id_seq RESTART WITH 1;"))
            await session.execute(text("ALTER SEQUENCE maintenance_ticket_assignments_assignment_id_seq RESTART WITH 1;"))
            await session.commit()
            logger.info("Reset PostgreSQL maintenance ticket sequence to 1.")
        except Exception as e:
            logger.warning(f"Sequence reset skipped (not Postgres or not needed): {e}")

        # 2. Get Employee ID for Fazal Saiyed or Paidamoyo Mapeka
        e_res = await session.execute(select(Employee).where((Employee.phone == "919265368695") | (Employee.phone == "263712127593")))
        emp = e_res.scalars().first()
        emp_id = emp.employee_id if emp else 1

        # 3. Get Category, Subcategory, IssueType
        c_res = await session.execute(select(Category).where(Category.domain.ilike("MAINTENANCE")))
        cat = c_res.scalars().first()
        cat_id = cat.category_id if cat else None

        sub_id = None
        issue_id = None
        if cat_id:
            s_res = await session.execute(select(Subcategory).where(Subcategory.category_id == cat_id))
            sub = s_res.scalars().first()
            sub_id = sub.subcategory_id if sub else None
            if sub_id:
                i_res = await session.execute(select(IssueType).where(IssueType.subcategory_id == sub_id))
                issue = i_res.scalars().first()
                issue_id = issue.issue_type_id if issue else None

        # 4. Create fresh Ticket 1: TKT-MNT-20260827-00001
        t_num = "TKT-MNT-20260827-00001"
        new_ticket = MaintenanceTicket(
            ticket_number=t_num,
            employee_id=emp_id,
            domain="MAINTENANCE",
            category_id=cat_id,
            subcategory_id=sub_id,
            issue_type_id=issue_id,
            room_area="Main Entrance / Front Area",
            description="Door latch jammed and won't lock properly",
            priority_id=3, # High
            status_id=1   # Open
        )
        session.add(new_ticket)
        await session.commit()
        logger.info(f"✅ Created fresh Building Projects Ticket #1: {t_num}")

        # 5. Fetch ticket with full relationships for notification
        stmt_full = (
            select(MaintenanceTicket)
            .options(
                selectinload(MaintenanceTicket.employee),
                selectinload(MaintenanceTicket.category),
                selectinload(MaintenanceTicket.subcategory),
                selectinload(MaintenanceTicket.issue_type),
                selectinload(MaintenanceTicket.priority)
            )
            .where(MaintenanceTicket.ticket_number == t_num)
        )
        t_obj = (await session.execute(stmt_full)).scalars().first()

        # 6. Fetch Projects Support Admins (Stanclea & Omar Arizai)
        admins_stmt = select(SupportAdmin).where(SupportAdmin.is_maintenance_admin == True, SupportAdmin.active == True)
        maint_admins = (await session.execute(admins_stmt)).scalars().all()

        emp_name = t_obj.employee.full_name if t_obj.employee else "Fazal Saiyed (Master Admin)"
        emp_phone = t_obj.employee.phone if t_obj.employee else "919265368695"
        cat_name = t_obj.category.category_name if t_obj.category else "Doors, Windows & Locks"
        sub_name = t_obj.subcategory.subcategory_name if t_obj.subcategory else "Door Latch & Hinges"
        issue_name = t_obj.issue_type.issue_name if t_obj.issue_type else "Door latch jammed / won't lock"
        priority_name = t_obj.priority.priority_name if t_obj.priority else "High"
        room_area = t_obj.room_area or "Main Entrance / Front Area"
        description = t_obj.description

        header = "🚨 NEW 🏗️ PROJECTS TICKET"
        body = (
            f"🎫 *Ticket ID:* `{t_num}`\n"
            f"👤 *Reporter:* {emp_name} (`+{emp_phone}`)\n"
            f"🏢 *Location:* Tagoneswa Hardware\n"
            f"📍 *Room / Area:* {room_area}\n"
            f"📌 *Category:* {cat_name} ➡️ {sub_name}\n"
            f"⚙️ *Issue:* {issue_name}\n"
            f"🚨 *Priority:* {priority_name}\n"
            f"📝 *Description:* {description}"
        )
        footer = "Tap button below to claim ticket"
        buttons = [
            {
                "id": f"claim_{t_num}",
                "title": "🔵 Claim Ticket"
            }
        ]

        admin_phones = [adm.phone for adm in maint_admins]
        if settings.master_admin_phone and settings.master_admin_phone not in admin_phones:
            admin_phones.append(settings.master_admin_phone)

        logger.info(f"Broadcasting Ticket {t_num} with Claim button to admins: {admin_phones}")
        for p in admin_phones:
            try:
                await meta_api.send_button_message(
                    to_phone=p,
                    body_text=body,
                    buttons=buttons,
                    header_text=header,
                    footer_text=footer
                )
                logger.info(f"✅ Alert with Claim button sent successfully to +{p}")
            except Exception as e:
                logger.error(f"Failed to send to +{p}: {e}")

async def cleanup_and_renumber():
    await reset_and_create_ticket_1()

if __name__ == "__main__":
    asyncio.run(reset_and_create_ticket_1())
