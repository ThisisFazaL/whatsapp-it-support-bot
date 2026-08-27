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
logger = logging.getLogger("cleanup_maint")

async def cleanup_and_renumber():
    logger.info("Connecting to database for maintenance ticket cleanup...")
    async with async_session_factory() as session:
        # Fetch all maintenance tickets
        stmt = select(MaintenanceTicket).order_by(MaintenanceTicket.ticket_id.asc())
        res = await session.execute(stmt)
        tickets = res.scalars().all()

        logger.info(f"Found {len(tickets)} maintenance tickets in DB.")
        for t in tickets:
            logger.info(f"Existing Ticket: ID={t.ticket_id}, Number={t.ticket_number}, Desc='{t.description[:40]}'")

        # Delete tickets 1, 2, 3, 4 or tickets created during testing
        # We delete any ticket whose ticket_id < 5 or ticket_number contains -00001, -00002, -00003, -00004
        to_delete_ids = [t.ticket_id for t in tickets if t.ticket_id < 5 or any(t.ticket_number.endswith(f"-0000{i}") for i in (1, 2, 3, 4))]
        target_ticket = None
        for t in tickets:
            if t.ticket_id >= 5 or t.ticket_number.endswith("-00005") or (t.ticket_id not in to_delete_ids):
                target_ticket = t
                break

        if not target_ticket and tickets:
            # Fallback to the latest ticket if target wasn't > 4
            target_ticket = tickets[-1]

        if to_delete_ids:
            # Delete assignments for deleted tickets
            await session.execute(delete(MaintenanceTicketAssignment).where(MaintenanceTicketAssignment.ticket_id.in_(to_delete_ids)))
            await session.execute(delete(MaintenanceTicket).where(MaintenanceTicket.ticket_id.in_(to_delete_ids)))
            await session.commit()
            logger.info(f"Deleted test maintenance tickets: {to_delete_ids}")

        # Re-fetch or update target ticket to Ticket #1 (TKT-MNT-20260827-00001)
        if target_ticket:
            target_ticket.ticket_number = "TKT-MNT-20260827-00001"
            await session.commit()
            logger.info(f"Updated Ticket ID {target_ticket.ticket_id} -> Number: TKT-MNT-20260827-00001")

            # Load full relationships for notification
            stmt_full = (
                select(MaintenanceTicket)
                .options(
                    selectinload(MaintenanceTicket.employee),
                    selectinload(MaintenanceTicket.category),
                    selectinload(MaintenanceTicket.subcategory),
                    selectinload(MaintenanceTicket.issue_type),
                    selectinload(MaintenanceTicket.priority),
                    selectinload(MaintenanceTicket.location)
                )
                .where(MaintenanceTicket.ticket_id == target_ticket.ticket_id)
            )
            t_obj = (await session.execute(stmt_full)).scalars().first()

            # Ensure ticket is assigned to Stanclea and Omar
            admins_stmt = select(SupportAdmin).where(SupportAdmin.is_maintenance_admin == True, SupportAdmin.active == True)
            maint_admins = (await session.execute(admins_stmt)).scalars().all()

            for adm in maint_admins:
                asg_stmt = select(MaintenanceTicketAssignment).where(
                    MaintenanceTicketAssignment.ticket_id == t_obj.ticket_id,
                    MaintenanceTicketAssignment.admin_id == adm.admin_id
                )
                existing_asg = (await session.execute(asg_stmt)).scalars().first()
                if not existing_asg:
                    session.add(MaintenanceTicketAssignment(ticket_id=t_obj.ticket_id, admin_id=adm.admin_id))
            await session.commit()

            # Prepare WhatsApp Alert
            emp_name = t_obj.employee.full_name if t_obj.employee else "Staff Reporter"
            emp_phone = t_obj.employee.phone if t_obj.employee else "N/A"
            loc_name = t_obj.location.location_name if t_obj.location else (t_obj.location_name or "Tagoneswa Hardware")
            cat_name = t_obj.category.category_name if t_obj.category else "Doors, Windows & Locks"
            sub_name = t_obj.subcategory.subcategory_name if t_obj.subcategory else "Door Latch & Hinges"
            issue_name = t_obj.issue_type.issue_name if t_obj.issue_type else "Custom Repair"
            priority_name = t_obj.priority.priority_name if t_obj.priority else "Medium"
            room_area = t_obj.room_area or "Main Entrance / Front Area"
            description = t_obj.description or "Building Projects repair request"

            hazard_notice = "\n⚠️ *SAFETY HAZARD:* 🚨 URGENT SAFETY HAZARD FLAG!" if getattr(t_obj, "is_safety_hazard", False) else ""

            header = "🚨 NEW 🏗️ PROJECTS TICKET"
            body = (
                f"🎫 *Ticket ID:* `TKT-MNT-20260827-00001`\n"
                f"👤 *Reporter:* {emp_name} (`+{emp_phone}`)\n"
                f"🏢 *Location:* {loc_name}\n"
                f"📍 *Room / Area:* {room_area}\n"
                f"📌 *Category:* {cat_name} ➡️ {sub_name}\n"
                f"⚙️ *Issue:* {issue_name}\n"
                f"🚨 *Priority:* {priority_name}{hazard_notice}\n"
                f"📝 *Description:* {description}"
            )
            footer = "Tap button below to resolve"
            buttons = [
                {
                    "id": "resolve_TKT-MNT-20260827-00001",
                    "title": "🟢 Resolve Ticket"
                }
            ]

            # Send to Stanclea and Omar Arizai
            admin_phones = [adm.phone for adm in maint_admins]
            if settings.master_admin_phone and settings.master_admin_phone not in admin_phones:
                admin_phones.append(settings.master_admin_phone)

            logger.info(f"Sending Ticket TKT-MNT-20260827-00001 alert to admins: {admin_phones}")
            for p in admin_phones:
                try:
                    if t_obj.image_id:
                        await meta_api.send_button_message(
                            to_phone=p,
                            body_text=body,
                            buttons=buttons,
                            header_text=header,
                            footer_text=footer,
                            image_id=t_obj.image_id
                        )
                    else:
                        await meta_api.send_button_message(
                            to_phone=p,
                            body_text=body,
                            buttons=buttons,
                            header_text=header,
                            footer_text=footer
                        )
                    logger.info(f"✅ Alert sent successfully to +{p}")
                except Exception as e:
                    logger.error(f"Failed to send to +{p}: {e}")

if __name__ == "__main__":
    asyncio.run(cleanup_and_renumber())
