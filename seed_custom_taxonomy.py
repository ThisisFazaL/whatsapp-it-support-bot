import asyncio
import logging
from sqlalchemy import select, delete
from app.database import (
    async_session_factory, Category, Subcategory, IssueType, engine
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("taxonomy")

TAXONOMY_TREE = [
    {
        "category": "IT & Computing Equipment",
        "subcategories": [
            {
                "name": "Computer & Laptop",
                "issues": [
                    "Display / Screen damage or flickering",
                    "Battery charging / Power failure",
                    "System slow / Operating System crash",
                    "Keyboard, Mouse, or Peripherals issue",
                    "Other Computer / Laptop Issue"
                ]
            },
            {
                "name": "Printers & Scanners",
                "issues": [
                    "Printer offline or unreachable",
                    "Paper jam / Printing alignment error",
                    "Toner replacement / Low ink",
                    "Other Printer / Scanner Issue"
                ]
            },
            {
                "name": "Desk Phone & Landline",
                "issues": [
                    "No dial tone / Line dead",
                    "Intercom extension not ringing",
                    "Poor audio quality / Static noise",
                    "Other Desk Phone / Landline Issue"
                ]
            },
            {
                "name": "Other IT / Computing Equipment",
                "issues": [
                    "Other IT / Hardware Problem (Explain in description)"
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
                    "Cannot connect to Office Wi-Fi",
                    "Wi-Fi connected but no internet access",
                    "Wi-Fi password prompt looping / Invalid credential",
                    "Other Wi-Fi Issue"
                ]
            },
            {
                "name": "LAN & Wired Ethernet",
                "issues": [
                    "Ethernet cable disconnected / Cable damaged",
                    "No IP address assigned (DHCP error)",
                    "Local Network / Shared drive unreachable",
                    "Other LAN Network Issue"
                ]
            },
            {
                "name": "Internet & Routers",
                "issues": [
                    "Extremely slow internet speed",
                    "Complete internet outage",
                    "Other Internet / Router Issue"
                ]
            },
            {
                "name": "Other Network & Connectivity",
                "issues": [
                    "Other Network Problem (Explain in description)"
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
                    "Camera video feed offline / Black screen",
                    "CCTV recording / Playback issue",
                    "Camera lens dirty / Position adjustment required",
                    "Other CCTV Issue"
                ]
            },
            {
                "name": "Biometric & Attendance Systems",
                "issues": [
                    "Fingerprint / Face ID scanner non-responsive",
                    "Punch time not syncing to Attendance software",
                    "RFID card reader error",
                    "Other Biometric / Attendance Issue"
                ]
            },
            {
                "name": "Access Control & Automatic Gates",
                "issues": [
                    "Automatic gate / Boom barrier not opening",
                    "Door magnetic lock stuck / Access denied",
                    "RFID card / Tag not recognized",
                    "Other Access Gate Issue"
                ]
            },
            {
                "name": "Intrusion & Security Alarms",
                "issues": [
                    "False alarm triggering / Continuous beeping",
                    "Alarm panel error / Battery low",
                    "Motion sensor / Glass break sensor faulty",
                    "Other Alarm System Issue"
                ]
            },
            {
                "name": "Other Security System",
                "issues": [
                    "Other Security System Problem (Explain in description)"
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
                    "Power socket dead / No electricity in workstation",
                    "Light fixture / LED tube flickering or dead",
                    "MCB breaker tripped / Short circuit spark",
                    "Other Electrical Fitting Issue"
                ]
            },
            {
                "name": "Inverters & UPS Power Backup",
                "issues": [
                    "Inverter battery backup failure / Short runtime",
                    "UPS continuously beeping / Alarm indicator",
                    "No power transition during power outage",
                    "Other Inverter / UPS Issue"
                ]
            },
            {
                "name": "Solar Power System",
                "issues": [
                    "Solar inverter error code on display",
                    "Low solar power generation",
                    "Solar panel / Wiring physical damage",
                    "Other Solar Power System Issue"
                ]
            },
            {
                "name": "Electronics & Power Supplies",
                "issues": [
                    "Electronic device power supply failure",
                    "Overheating / Burning smell from equipment",
                    "Other Electronics Issue"
                ]
            },
            {
                "name": "Other Electrical / Power",
                "issues": [
                    "Other Electrical Problem (Explain in description)"
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
                    "General Equipment Repair",
                    "Office Furniture / Desk / Chair Repair",
                    "Other Custom Issue (Explain in description)"
                ]
            }
        ]
    }
]

async def seed_taxonomy():
    logger.info("Seeding custom category, subcategory, and issue taxonomy...")
    async with async_session_factory() as session:
        # Clear existing test tickets and assignments to re-seed taxonomy cleanly
        from app.database import TicketAssignment, Ticket
        await session.execute(delete(TicketAssignment))
        await session.execute(delete(Ticket))
        await session.execute(delete(IssueType))
        await session.execute(delete(Subcategory))
        await session.execute(delete(Category))
        await session.commit()

        for cat_data in TAXONOMY_TREE:
            cat = Category(category_name=cat_data["category"], active=True)
            session.add(cat)
            await session.flush()

            for sub_data in cat_data["subcategories"]:
                sub = Subcategory(category_id=cat.category_id, subcategory_name=sub_data["name"], active=True)
                session.add(sub)
                await session.flush()

                for issue_title in sub_data["issues"]:
                    iss = IssueType(subcategory_id=sub.subcategory_id, issue_name=issue_title, active=True)
                    session.add(iss)

        await session.commit()
    logger.info("✅ Custom taxonomy seeded successfully into PostgreSQL!")

if __name__ == "__main__":
    asyncio.run(seed_taxonomy())
