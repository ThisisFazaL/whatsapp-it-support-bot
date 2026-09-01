import asyncio
import os
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings
from app.database import Base
from app.workshop.models import (
    WorkshopTruck, WorkshopStaff, WorkshopCategory, WorkshopSubcategory,
    WorkshopTicket, WorkshopPartsRequest
)

async def seed_workshop_data_in_session(session: AsyncSession):
    """Idempotently seeds trucks, staff, and fault taxonomies in an active session."""
    # 1. Seed Trucks
    trucks = [
        {"truck_number": "1045", "plate_number": "ABZ 1045", "model_make": "Volvo FH16 540", "body_type": "Horse (6x4)", "home_depot": "Harare Central"},
        {"truck_number": "1046", "plate_number": "ACY 2046", "model_make": "Scania R500", "body_type": "Horse (6x4)", "home_depot": "Bulawayo Yard"},
        {"truck_number": "2012", "plate_number": "AEN 2012", "model_make": "Shacman F3000", "body_type": "20m³ Tipper", "home_depot": "Mine Site A"},
        {"truck_number": "3005", "plate_number": "AFG 3005", "model_make": "Mercedes-Benz Actros 3340", "body_type": "Fuel Tanker", "home_depot": "Beira Corridor"},
        {"truck_number": "4010", "plate_number": "AGH 4010", "model_make": "Isuzu FTR 850", "body_type": "8-Ton Rigid", "home_depot": "Harare Central"},
    ]
    
    for t in trucks:
        stmt = select(WorkshopTruck).where(WorkshopTruck.truck_number == t["truck_number"])
        existing = (await session.execute(stmt)).scalars().first()
        if not existing:
            session.add(WorkshopTruck(**t))

    # 2. Seed Staff
    staff_members = [
        {"full_name": "Panashe Mutasa (Clerk)", "phone": "919876543220", "role": "CLERK"},
        {"full_name": "Edward Marufu (Logistics Supervisor)", "phone": "919876543221", "role": "SUPERVISOR"},
        {"full_name": "Blessing Moyo (Mechanic)", "phone": "919876543222", "role": "MECHANIC"},
        {"full_name": "Farai Shumba (Workshop Lead)", "phone": "919876543223", "role": "LEAD"},
        {"full_name": "Purchasing & Procurement Team", "phone": "919876543224", "role": "PURCHASING"},
        {"full_name": "Fazal Saiyed (Master Admin)", "phone": "919265368695", "role": "SUPERVISOR"},
    ]

    for s in staff_members:
        stmt = select(WorkshopStaff).where(WorkshopStaff.phone == s["phone"])
        existing = (await session.execute(stmt)).scalars().first()
        if not existing:
            session.add(WorkshopStaff(**s))
        else:
            existing.active = True

    # 3. Seed Categories & Subcategories
    taxonomy = [
        ("Brakes & Air Pressure", ["Air Pressure Leak", "Foot Brake Spongy / Low Air", "Handbrake / Maxie Stuck", "Air Compressor / Dryer Issue"]),
        ("Engine, Fuel & Cooling", ["Engine Overheating", "Low Oil Pressure Warning", "Diesel Starvation / Fuel Leak", "Loss of Power / Turbo Noise"]),
        ("Electrical, Lights & Battery", ["Battery Dead / No Crank", "Alternator Warning Light", "Headlights / Tail Lights Failed", "Starter Motor Click"]),
        ("Transmission & Clutch", ["Gearbox Grinding / Stiff", "Clutch Slipping", "Propshaft Vibration", "Differential Noise"]),
        ("Suspension, Steering & Axles", ["Air Bag Deflated", "Kingpin Play / Steering Stiff", "Leaf Spring Broken", "Wheel Alignment / Pulling"]),
        ("Tires, Wheels & Rims", ["Flat / Blown Tire", "Wheel Nut Loose / Stud Broken", "Rim Crack / Damage", "Wheel Bearing Grinding"]),
        ("Trailer & Cargo Body", ["Trailer Brake Lockup", "Fifth Wheel / Turntable Play", "Landing Gear Jammed", "Curtain / Door Latch Broken"]),
        ("Refrigeration Unit (Reefer)", ["Reefer Engine Failure", "Temperature Warning / Gas Leak", "Drive Belt Snapped"])
    ]

    for cat_name, subcats in taxonomy:
        stmt = select(WorkshopCategory).where(WorkshopCategory.category_name == cat_name)
        cat_obj = (await session.execute(stmt)).scalars().first()
        if not cat_obj:
            cat_obj = WorkshopCategory(category_name=cat_name)
            session.add(cat_obj)
            await session.flush()
        
        for sub_name in subcats:
            sub_stmt = select(WorkshopSubcategory).where(
                WorkshopSubcategory.category_id == cat_obj.category_id,
                WorkshopSubcategory.subcategory_name == sub_name
            )
            existing_sub = (await session.execute(sub_stmt)).scalars().first()
            if not existing_sub:
                session.add(WorkshopSubcategory(category_id=cat_obj.category_id, subcategory_name=sub_name))

    await session.commit()

async def seed_workshop():
    db_urls = [settings.database_url, "sqlite+aiosqlite:///./itsupport.db"]
    engine = None
    connected_url = None

    for url in db_urls:
        try:
            kw = {"echo": False}
            if "postgresql" in url:
                kw["connect_args"] = {"ssl": "require", "statement_cache_size": 0, "prepared_statement_cache_size": 0}
            test_engine = create_async_engine(url, **kw)
            async with test_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            engine = test_engine
            connected_url = url
            break
        except Exception as e:
            print(f"Connection to {url} failed: {e}. Trying fallback...")

    if not engine:
        raise RuntimeError("Could not connect to any database.")

    print(f"Connected to DB: {connected_url}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        await seed_workshop_data_in_session(session)
        print("Workshop trucks, staff, and taxonomy seeded successfully!")

if __name__ == "__main__":
    asyncio.run(seed_workshop())
