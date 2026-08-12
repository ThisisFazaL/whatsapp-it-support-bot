import asyncio
import logging
from sqlalchemy import select, delete, text
from app.database import (
    async_session_factory, Category, Subcategory, IssueType, TicketAssignment, Ticket,
    SupportAdmin, AdminCategoryMapping, engine
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed_exact")

EXACT_TAXONOMY = [
    {
        "category": "IT & Computing Equipment",
        "subcategories": [
            {
                "name": "Computer & Laptop",
                "issues": [
                    "Display damage",
                    "Power failure",
                    "System crash",
                    "Peripherals",
                    "Other"
                ]
            },
            {
                "name": "Printers & Scanners",
                "issues": [
                    "Printer offline",
                    "Paper jam",
                    "Toner replacement",
                    "Other"
                ]
            },
            {
                "name": "Desk Phone & Landline",
                "issues": [
                    "No dial tone",
                    "Intercom error",
                    "Audio noise",
                    "Other"
                ]
            },
            {
                "name": "Other IT Equipment",
                "issues": [
                    "Describe in next step"
                ]
            }
        ]
    },
    {
        "category": "Networking & Connectivity",
        "subcategories": [
            {
                "name": "Wi-Fi & Wireless Network",
                "issues": [
                    "Cannot connect",
                    "Password loop",
                    "Slow Wi-Fi",
                    "Other"
                ]
            },
            {
                "name": "LAN & Wired Ethernet",
                "issues": [
                    "Cable disconnected",
                    "No IP address",
                    "Local network down",
                    "Other"
                ]
            },
            {
                "name": "Internet & Routers",
                "issues": [
                    "Slow internet",
                    "Outage",
                    "Other"
                ]
            },
            {
                "name": "Other Network Issue",
                "issues": [
                    "Describe in next step"
                ]
            }
        ]
    },
    {
        "category": "Security & Access Control Systems",
        "subcategories": [
            {
                "name": "CCTV & Surveillance Cameras",
                "issues": [
                    "Camera offline",
                    "Playback issue",
                    "Position adjustment",
                    "Other"
                ]
            },
            {
                "name": "Biometric & Attendance Systems",
                "issues": [
                    "Fingerprint/Face scanner fail",
                    "Attendance sync error",
                    "Other"
                ]
            },
            {
                "name": "Access Control & Automatic Gates",
                "issues": [
                    "Gate/Barrier not opening",
                    "RFID card blocked",
                    "Other"
                ]
            },
            {
                "name": "Intrusion & Security Alarms",
                "issues": [
                    "False alarm",
                    "Beeping sound",
                    "Sensor error",
                    "Other"
                ]
            },
            {
                "name": "Other Security System",
                "issues": [
                    "Describe in next step"
                ]
            }
        ]
    },
    {
        "category": "Electrical & Power Systems",
        "subcategories": [
            {
                "name": "Electrical Fittings & Wiring",
                "issues": [
                    "Socket dead",
                    "Lights flickering",
                    "MCB breaker tripped",
                    "Other"
                ]
            },
            {
                "name": "Inverters & UPS Power Backup",
                "issues": [
                    "Battery failure",
                    "Beeping sound",
                    "No power transition",
                    "Other"
                ]
            },
            {
                "name": "Solar Power System",
                "issues": [
                    "Inverter error code",
                    "Low generation",
                    "Panel damage",
                    "Other"
                ]
            },
            {
                "name": "Electronics & Power Supplies",
                "issues": [
                    "Power supply failure",
                    "Overheating",
                    "Other"
                ]
            },
            {
                "name": "Other Electrical Issue",
                "issues": [
                    "Describe in next step"
                ]
            }
        ]
    },
    {
        "category": "Other / Custom Support Request",
        "subcategories": [
            {
                "name": "General Maintenance & Facilities",
                "issues": [
                    "General repair",
                    "Desk/Chair repair",
                    "Custom issue"
                ]
            }
        ]
    }
]

async def seed_exact():
    logger.info("Seeding exact custom taxonomy...")
    async with async_session_factory() as session:
        # Clear tickets, mappings, and previous taxonomy
        await session.execute(delete(TicketAssignment))
        await session.execute(delete(Ticket))
        await session.execute(delete(AdminCategoryMapping))
        await session.execute(delete(IssueType))
        await session.execute(delete(Subcategory))
        await session.execute(delete(Category))
        await session.commit()

        new_categories = []
        for cat_item in EXACT_TAXONOMY:
            cat = Category(category_name=cat_item["category"], active=True)
            session.add(cat)
            await session.flush()
            new_categories.append(cat)

            for sub_item in cat_item["subcategories"]:
                sub = Subcategory(category_id=cat.category_id, subcategory_name=sub_item["name"], active=True)
                session.add(sub)
                await session.flush()

                for iss_title in sub_item["issues"]:
                    iss = IssueType(subcategory_id=sub.subcategory_id, issue_name=iss_title, active=True)
                    session.add(iss)

        # Re-map Fazal (Master Admin) to all newly created categories
        fazal_phone = "919265368695"
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

        for cat in new_categories:
            session.add(AdminCategoryMapping(admin_id=fazal_admin.admin_id, category_id=cat.category_id))

        await session.commit()

    # Sync sequences
    async with engine.begin() as conn:
        for tbl, seq in [
            ("categories", "categories_category_id_seq"),
            ("subcategories", "subcategories_subcategory_id_seq"),
            ("issue_types", "issue_types_issue_type_id_seq")
        ]:
            try:
                await conn.execute(text(f"SELECT setval('{seq}', (SELECT MAX({tbl[:-1]}_id) FROM {tbl}), true);"))
            except Exception:
                pass

    logger.info("✅ Exact taxonomy seeded and admin mapped successfully!")

if __name__ == "__main__":
    asyncio.run(seed_exact())
