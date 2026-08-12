import asyncio
import logging
from sqlalchemy import select, delete
from app.database import (
    async_session_factory, SupportAdmin, AdminCategoryMapping, Category
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("set_fazal_admin")

async def set_fazal_master_admin():
    async with async_session_factory() as session:
        fazal_phone = "919265368695"
        
        # 1. Fetch or Create Fazal Admin Record
        stmt_adm = select(SupportAdmin).where(SupportAdmin.phone == fazal_phone)
        fazal_admin = (await session.execute(stmt_adm)).scalars().first()

        if not fazal_admin:
            fazal_admin = SupportAdmin(
                full_name="Fazal Saiyed (Primary Support Admin)",
                phone=fazal_phone,
                is_master_admin=True,
                active=True
            )
            session.add(fazal_admin)
            await session.flush()
            logger.info("Created SupportAdmin record for Fazal.")
        else:
            fazal_admin.full_name = "Fazal Saiyed (Primary Support Admin)"
            fazal_admin.is_master_admin = True
            fazal_admin.active = True
            logger.info("Updated SupportAdmin record for Fazal.")

        # 2. Get all categories
        cat_stmt = select(Category).where(Category.active == True)
        all_categories = (await session.execute(cat_stmt)).scalars().all()

        # 3. Clear old category mappings
        await session.execute(delete(AdminCategoryMapping))
        await session.flush()

        # 4. Map Fazal to EVERY category so he receives all ticket alerts!
        for cat in all_categories:
            mapping = AdminCategoryMapping(
                admin_id=fazal_admin.admin_id,
                category_id=cat.category_id
            )
            session.add(mapping)

        await session.commit()
    logger.info(f"✅ Fazal ({fazal_phone}) is now the Primary Active Support Admin for ALL {len(all_categories)} categories!")

if __name__ == "__main__":
    asyncio.run(set_fazal_master_admin())
