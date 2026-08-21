import asyncio
import logging
from sqlalchemy import select, text
from app.database import async_session_factory, SupportAdmin, Employee, engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("update_maint_roles")

async def update_roles():
    logger.info("Updating Maintenance Admins and Reporters...")
    
    async with async_session_factory() as session:
        # 1. Remove Kevin Chikati from Maintenance Reporters
        kevin_stmt = select(Employee).where(Employee.phone == "263718627526")
        kevin = (await session.execute(kevin_stmt)).scalars().first()
        if kevin:
            kevin.is_maintenance_reporter = False
            logger.info("Removed Kevin Chikati (+263 71 862 7526) from Maintenance Reporters.")

        # 2. Add / Update Maintenance Admins: Stanclea & Omar Arizai
        new_maint_admins = [
            {"name": "Stanclea", "phone": "263780099291"},
            {"name": "Omar Arizai", "phone": "26377133602"}
        ]

        # Deactivate old test maintenance admins if any
        old_maint_stmt = select(SupportAdmin).where(SupportAdmin.phone.in_(["263771112222", "263773334444"]))
        old_admins = (await session.execute(old_maint_stmt)).scalars().all()
        for oa in old_admins:
            oa.is_maintenance_admin = False

        for ma in new_maint_admins:
            phone = ma["phone"]
            name = ma["name"]
            
            stmt = select(SupportAdmin).where(SupportAdmin.phone == phone)
            adm = (await session.execute(stmt)).scalars().first()
            if adm:
                adm.full_name = name
                adm.is_maintenance_admin = True
                adm.active = True
                logger.info(f"Updated Maintenance Admin: '{name}' ({phone})")
            else:
                session.add(SupportAdmin(
                    full_name=name,
                    phone=phone,
                    is_master_admin=False,
                    is_maintenance_admin=True,
                    active=True
                ))
                logger.info(f"Registered New Maintenance Admin: '{name}' ({phone})")

        await session.commit()
    
    # Sync PostgreSQL sequences
    async with engine.begin() as conn:
        try:
            await conn.execute(text("SELECT setval('support_admins_admin_id_seq', COALESCE((SELECT MAX(admin_id) FROM support_admins), 0) + 1, false);"))
        except Exception:
            pass

    logger.info("✅ Maintenance admins updated successfully!")

if __name__ == "__main__":
    asyncio.run(update_roles())
