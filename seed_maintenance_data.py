import asyncio
import logging
from sqlalchemy import select
from app.database import (
    async_session_factory, Category, Subcategory, IssueType,
    SupportAdmin, Employee, Department, Location, init_db_models
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed_maint")

async def seed_maintenance_data_in_session(session):
    """Seeds or syncs Building Projects categories, subcategories, issues, and admin roles."""
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
        },
        {
            "name": "Renovation & Expansion",
            "subcategories": [
                {
                    "name": "Structural & Partitioning",
                    "issues": ["New wall / drywall partition request", "Room extension / expansion work", "Demolition / wall removal request"]
                },
                {
                    "name": "Flooring, Tiling & Paint Work",
                    "issues": ["New floor tiling / repaving", "Full room repainting request", "Ceiling & roof modification"]
                },
                {
                    "name": "Electrical & Plumbing Fitting",
                    "issues": ["New electrical wiring & socket installation", "Plumbing fixture relocation / new installation", "General site upgrade / refurbishment"]
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
    logger.info("✅ Maintenance / Building Projects categories (including Renovation & Expansion) synced successfully!")

async def seed_maintenance_data():
    logger.info("Initializing DB models and seeding Maintenance data...")
    await init_db_models()
    async with async_session_factory() as session:
        await seed_maintenance_data_in_session(session)

if __name__ == "__main__":
    asyncio.run(seed_maintenance_data())
