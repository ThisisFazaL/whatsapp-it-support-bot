import asyncio
import logging
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.database import (
    async_session_factory, MaintenanceTicket, MaintenanceTicketAssignment,
    SupportAdmin, Employee, Category, Subcategory, IssueType, Priority
)
from app.meta_api import meta_api
from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("zayn_ticket")

async def create_zayn_ticket_and_notify():
    logger.info("Creating Zayn's Building Projects Ticket (TKT-MNT-20260831-00001)...")
    try:
        async with async_session_factory() as session:
            # 1. Fetch Zayn's employee record
            e_res = await session.execute(select(Employee).where((Employee.phone == "263713866223") | (Employee.full_name.ilike("%zayn%"))))
            zayn_emp = e_res.scalars().first()
            if not zayn_emp:
                zayn_emp = Employee(
                    employee_code="EMP_MNT_6223",
                    full_name="Zayn",
                    phone="263713866223",
                    is_maintenance_reporter=True,
                    active=True
                )
                session.add(zayn_emp)
                await session.flush()
            else:
                zayn_emp.is_maintenance_reporter = True
                zayn_emp.active = True

            # 2. Fetch Category, Subcategory, IssueType
            c_res = await session.execute(select(Category).where(Category.domain.ilike("MAINTENANCE")))
            cat = c_res.scalars().first()
            cat_id = cat.category_id if cat else None

            s_res = await session.execute(select(Subcategory))
            sub = s_res.scalars().first()
            sub_id = sub.subcategory_id if sub else None

            i_res = await session.execute(select(IssueType))
            issue = i_res.scalars().first()
            issue_id = issue.issue_type_id if issue else None

            t_num = "TKT-MNT-20260831-00001"
            
            # Check if already exists
            chk_res = await session.execute(select(MaintenanceTicket).where(MaintenanceTicket.ticket_number == t_num))
            t_obj = chk_res.scalars().first()

            if not t_obj:
                t_obj = MaintenanceTicket(
                    ticket_number=t_num,
                    employee_id=zayn_emp.employee_id,
                    domain="MAINTENANCE",
                    category_id=cat_id,
                    subcategory_id=sub_id,
                    issue_type_id=issue_id,
                    room_area="Block 1 gents toilet door down stairs",
                    description="Block one gents toilet door down stairs hindge Broken so the door isn't closing right",
                    priority_id=2, # Medium
                    status_id=1   # Open
                )
                session.add(t_obj)
                await session.commit()
                logger.info(f"✅ Created ticket {t_num} in PostgreSQL database!")
            else:
                t_obj.status_id = 1
                t_obj.description = "Block one gents toilet door down stairs hindge Broken so the door isn't closing right"
                t_obj.room_area = "Block 1 gents toilet door down stairs"
                await session.commit()
                logger.info(f"Updated existing ticket {t_num}")

            # 3. Reload full relationships
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

            # 4. Fetch Projects Support Admins (Stanclea & Omar Arizai)
            admins_stmt = select(SupportAdmin).where(SupportAdmin.is_maintenance_admin == True, SupportAdmin.active == True)
            maint_admins = (await session.execute(admins_stmt)).scalars().all()

            emp_name = t_obj.employee.full_name if (t_obj and t_obj.employee) else "Zayn"
            emp_phone = t_obj.employee.phone if (t_obj and t_obj.employee) else "263713866223"
            cat_name = t_obj.category.category_name if (t_obj and t_obj.category) else "Doors, Windows & Locks"
            sub_name = t_obj.subcategory.subcategory_name if (t_obj and t_obj.subcategory) else "Door Latch & Hinges"
            issue_name = t_obj.issue_type.issue_name if (t_obj and t_obj.issue_type) else "Door hinges squeaking or misaligned"
            priority_name = t_obj.priority.priority_name if (t_obj and t_obj.priority) else "Medium"
            room_area = t_obj.room_area or "Block 1 gents toilet door down stairs"
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

            logger.info(f"Broadcasting Ticket {t_num} to Projects Admins: {admin_phones}")
            for p in admin_phones:
                try:
                    await meta_api.send_button_message(
                        to_phone=p,
                        body_text=body,
                        buttons=buttons,
                        header_text=header,
                        footer_text=footer
                    )
                    logger.info(f"✅ Ticket alert with Claim button sent to +{p}")
                except Exception as e:
                    logger.error(f"Failed to send to +{p}: {e}")
            return {"status": "success", "ticket": t_num, "admins_notified": admin_phones}
    except Exception as exc:
        logger.error(f"Error creating Zayn ticket: {exc}", exc_info=True)
        return {"status": "error", "error": str(exc)}

if __name__ == "__main__":
    asyncio.run(create_zayn_ticket_and_notify())
