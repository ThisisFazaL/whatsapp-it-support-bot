import asyncio
import logging
from sqlalchemy import select
from app.database import (
    async_session_factory, Category, Subcategory, IssueType,
    SupportAdmin, Employee, Department, Location, init_db_models
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed_maint")

async def seed_maintenance_data():
    logger.info("Initializing DB models and seeding Maintenance data...")
    await init_db_models()

    async with async_session_factory() as session:
        # 1. Seed Maintenance Categories, Subcategories, and Issues
        maint_categories = [
            {
                "name": "Doors, Windows & Locks",
                "subcategories": [
                    {
                        "name": "Door Latch & Hinges",
                        "issues": ["Door latch jammed / won't lock", "Door hinges squeaking or misaligned", "Glass door closer leaking oil"]
                    },
                    {
                        "name": "Windows & Blinds",
                        "issues": ["Window glass cracked or loose", "Window blind cord snapped", "Window latch broken"]
                    }
                ]
            },
            {
                "name": "Ceiling, Walls & Roofing",
                "subcategories": [
                    {
                        "name": "Ceiling Tiles & Leaks",
                        "issues": ["Water leaking from ceiling tile", "Ceiling tile sagging or broken", "Roof leak during rain"]
                    },
                    {
                        "name": "Wall Damage & Paint",
                        "issues": ["Drywall hole or crack", "Wall paint peeling", "Baseboard loose"]
                    }
                ]
            },
            {
                "name": "Electrical & Lighting",
                "subcategories": [
                    {
                        "name": "Lighting & Fixtures",
                        "issues": ["Fluorescent tube / LED light flickering", "Emergency light battery warning", "Light switch broken"]
                    },
                    {
                        "name": "Power Sockets & Wiring",
                        "issues": ["Wall socket non-functional", "Exposed electrical wire (Hazard)", "Circuit breaker tripping repeatedly"]
                    }
                ]
            },
            {
                "name": "Plumbing & Water Leakage",
                "subcategories": [
                    {
                        "name": "Restroom Plumbing",
                        "issues": ["Restroom tap leaking constantly", "Toilet flush mechanism broken", "Restroom drain clogged"]
                    },
                    {
                        "name": "Water Supply & Dispensers",
                        "issues": ["Water dispenser leaking", "Low water pressure", "Pipe joint dripping"]
                    }
                ]
            },
            {
                "name": "General Building & Furniture",
                "subcategories": [
                    {
                        "name": "Furniture & Workstations",
                        "issues": ["Office chair wheel/lever broken", "Desk drawer lock jammed", "Cabinet door loose"]
                    },
                    {
                        "name": "HVAC & Ventilation",
                        "issues": ["AC unit dripping water", "AC ventilation grill dirty", "Exhaust fan noisy"]
                    }
                ]
            }
        ]

        for cat_dict in maint_categories:
            c_res = await session.execute(select(Category).where(Category.category_name == cat_dict["name"]))
            cat_obj = c_res.scalars().first()
            if not cat_obj:
                cat_obj = Category(category_name=cat_dict["name"], domain="MAINTENANCE", active=True)
                session.add(cat_obj)
                await session.flush()
            else:
                cat_obj.domain = "MAINTENANCE"

            for sub_dict in cat_dict["subcategories"]:
                s_res = await session.execute(select(Subcategory).where(Subcategory.subcategory_name == sub_dict["name"], Subcategory.category_id == cat_obj.category_id))
                sub_obj = s_res.scalars().first()
                if not sub_obj:
                    sub_obj = Subcategory(category_id=cat_obj.category_id, subcategory_name=sub_dict["name"], active=True)
                    session.add(sub_obj)
                    await session.flush()

                for issue_str in sub_dict["issues"]:
                    i_res = await session.execute(select(IssueType).where(IssueType.issue_name == issue_str, IssueType.subcategory_id == sub_obj.subcategory_id))
                    if not i_res.scalars().first():
                        session.add(IssueType(subcategory_id=sub_obj.subcategory_id, issue_name=issue_str, active=True))

        await session.commit()

        # 2. Seed 2 Maintenance Support Admins
        maint_admins = [
            {"name": "Blessing Moyo (Maintenance Lead)", "phone": "263771112222", "is_master": False, "is_maint": True},
            {"name": "Tafadzwa Banda (Facilities Tech)", "phone": "263773334444", "is_master": False, "is_maint": True},
        ]
        for ma in maint_admins:
            a_res = await session.execute(select(SupportAdmin).where(SupportAdmin.phone == ma["phone"]))
            existing_adm = a_res.scalars().first()
            if existing_adm:
                existing_adm.full_name = ma["name"]
                existing_adm.is_maintenance_admin = True
                existing_adm.active = True
            else:
                session.add(SupportAdmin(
                    full_name=ma["name"],
                    phone=ma["phone"],
                    is_master_admin=ma["is_master"],
                    is_maintenance_admin=True,
                    active=True
                ))
        await session.commit()

        # 3. Enable Maintenance Reporter status for Kevin Chikati and Fazal Saiyed (Dual-Role test users)
        reporters = ["263718627526", "919265368695"] # Kevin & Fazal
        for r_phone in reporters:
            e_res = await session.execute(select(Employee).where(Employee.phone == r_phone))
            emp = e_res.scalars().first()
            if emp:
                emp.is_maintenance_reporter = True
            else:
                # Ensure Kevin is in Employee table as well as SupportAdmin table if needed
                name = "Kevin Chikati" if r_phone == "263718627526" else "Fazal Saiyed"
                session.add(Employee(
                    employee_code=f"EMP_{r_phone}",
                    full_name=name,
                    phone=r_phone,
                    is_maintenance_reporter=True,
                    active=True
                ))
        await session.commit()
        logger.info("✅ Maintenance data and roles seeded successfully!")

if __name__ == "__main__":
    asyncio.run(seed_maintenance_data())
