import asyncio
import logging
from sqlalchemy import select, delete
from app.database import (
    async_session_factory, SupportAdmin, AdminCategoryMapping, Subcategory, Category
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed_admins")

ADMIN_ROSTER = [
    {
        "name": "Kevin Chikati",
        "phone": "263718627526",
        "subcategories": [
            "Computer & Laptop",
            "Other IT Equipment",
            "Wi-Fi & Wireless Network",
            "Internet & Routers"
        ]
    },
    {
        "name": "Ellias Murenga",
        "phone": "263788843579",
        "subcategories": [
            "Printers & Scanners",
            "LAN & Wired Ethernet",
            "Other Network Issue"
        ]
    },
    {
        "name": "Faisal Kassim",
        "phone": "263780100503",
        "subcategories": [
            "Desk Phone & Landline",
            "CCTV & Surveillance Cameras",
            "Biometric & Attendance Systems",
            "Access Control & Automatic Gates",
            "Intrusion & Security Alarms",
            "Other Security System",
            "Electrical Fittings & Wiring",
            "Inverters & UPS Power Backup",
            "Solar Power System",
            "Electronics & Power Supplies",
            "Other Electrical Issue",
            "General Maintenance & Facilities"
        ]
    }
]

async def seed_admin_matrix():
    logger.info("Ingesting active support admins and 1:1 subcategory routing matrix...")
    async with async_session_factory() as session:
        # Clear old mappings
        await session.execute(delete(AdminCategoryMapping))
        await session.flush()

        # Ingest/Update Fazal (Master Admin)
        fazal_phone = "919265368695"
        stmt_faz = select(SupportAdmin).where(SupportAdmin.phone == fazal_phone)
        fazal_adm = (await session.execute(stmt_faz)).scalars().first()
        if not fazal_adm:
            fazal_adm = SupportAdmin(
                full_name="Fazal Saiyed (Master Admin)",
                phone=fazal_phone,
                is_master_admin=True,
                active=True
            )
            session.add(fazal_adm)
            await session.flush()
        else:
            fazal_adm.is_master_admin = True
            fazal_adm.active = True

        # Ingest 3 Support Admins & Mappings
        for adm_info in ADMIN_ROSTER:
            phone = adm_info["phone"]
            stmt = select(SupportAdmin).where(SupportAdmin.phone == phone)
            adm = (await session.execute(stmt)).scalars().first()
            if not adm:
                adm = SupportAdmin(
                    full_name=adm_info["name"],
                    phone=phone,
                    is_master_admin=False,
                    active=True
                )
                session.add(adm)
                await session.flush()
            else:
                adm.full_name = adm_info["name"]
                adm.active = True

            # Map subcategories
            for sub_name in adm_info["subcategories"]:
                stmt_sub = select(Subcategory).where(Subcategory.subcategory_name == sub_name)
                sub_obj = (await session.execute(stmt_sub)).scalars().first()
                if sub_obj:
                    mapping = AdminCategoryMapping(
                        admin_id=adm.admin_id,
                        category_id=sub_obj.category_id,
                        subcategory_id=sub_obj.subcategory_id
                    )
                    session.add(mapping)

        await session.commit()
    logger.info("✅ All 3 Support Admins and 1:1 Subcategory Routing Matrix configured successfully!")

if __name__ == "__main__":
    asyncio.run(seed_admin_matrix())
