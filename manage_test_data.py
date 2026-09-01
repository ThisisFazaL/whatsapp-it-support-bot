import asyncio
import os
import sys
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.config import settings
from app.database import Base
from app.workshop.models import (
    WorkshopTruck, WorkshopStaff, WorkshopCategory, WorkshopSubcategory,
    WorkshopTicket, WorkshopPartsRequest
)
from app.state_manager import clear_user_state

TEST_TRUCK_NUMBER = "9999"
TEST_PHONES = {
    "clerk": "918200713637",
    "mechanic": "917859991843",
    "supervisor": "919265368695"
}

async def seed_test_database_in_session(session: AsyncSession):
    """Seeds only the requested test truck and test staff numbers."""
    # 1. Fake Truck
    stmt = select(WorkshopTruck).where(WorkshopTruck.truck_number == TEST_TRUCK_NUMBER)
    truck = (await session.execute(stmt)).scalars().first()
    if not truck:
        truck = WorkshopTruck(
            truck_number=TEST_TRUCK_NUMBER,
            plate_number="TST 9999",
            model_make="Volvo FH16 (Testing Unit)",
            body_type="Horse (6x4)",
            home_depot="Harare Test Bay",
            active=True
        )
        session.add(truck)
    else:
        truck.active = True

    # 2. Test Staff
    staff_data = [
        {"full_name": "Test Clerk", "phone": TEST_PHONES["clerk"], "role": "CLERK"},
        {"full_name": "Test Mechanic", "phone": TEST_PHONES["mechanic"], "role": "MECHANIC"},
        {"full_name": "Fazal Saiyed (Supervisor)", "phone": TEST_PHONES["supervisor"], "role": "SUPERVISOR"},
    ]

    for s in staff_data:
        stmt_s = select(WorkshopStaff).where(WorkshopStaff.phone == s["phone"])
        existing = (await session.execute(stmt_s)).scalars().first()
        if not existing:
            session.add(WorkshopStaff(**s))
        else:
            existing.full_name = s["full_name"]
            existing.role = s["role"]
            existing.active = True

    # 3. Ensure Basic Categories exist
    cat_stmt = select(WorkshopCategory)
    cats = (await session.execute(cat_stmt)).scalars().all()
    if not cats:
        from seed_workshop_data import seed_workshop_data_in_session
        await seed_workshop_data_in_session(session)

    await session.commit()
    print("[OK] Test Truck (#9999) and Test Staff seeded successfully!")

async def delete_test_data_in_session(session: AsyncSession):
    """Deletes all test tickets, parts requests, fake truck, and test staff."""
    # 1. Find Test Truck
    stmt_t = select(WorkshopTruck).where(WorkshopTruck.truck_number == TEST_TRUCK_NUMBER)
    truck = (await session.execute(stmt_t)).scalars().first()
    
    # 2. Delete test tickets
    if truck:
        stmt_tkt = select(WorkshopTicket).where(WorkshopTicket.truck_id == truck.truck_id)
        tkts = (await session.execute(stmt_tkt)).scalars().all()
        for t in tkts:
            await session.execute(delete(WorkshopPartsRequest).where(WorkshopPartsRequest.ticket_id == t.ticket_id))
            await session.delete(t)
        await session.delete(truck)

    # 3. Delete test clerk & mechanic (Keep supervisor active)
    for role_key in ["clerk", "mechanic"]:
        phone = TEST_PHONES[role_key]
        await session.execute(delete(WorkshopStaff).where(WorkshopStaff.phone == phone))
        await clear_user_state(session, phone)

    await clear_user_state(session, TEST_PHONES["supervisor"])
    await session.commit()
    print("[OK] All test data (Fake truck #9999, test tickets, and test staff) deleted cleanly!")

async def main(action: str = "seed"):
    db_urls = [settings.database_url, "sqlite+aiosqlite:///./itsupport.db"]
    engine = None

    for url in db_urls:
        try:
            kw = {"echo": False}
            if "postgresql" in url:
                kw["connect_args"] = {"ssl": "require", "statement_cache_size": 0, "prepared_statement_cache_size": 0}
            test_engine = create_async_engine(url, **kw)
            async with test_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            engine = test_engine
            break
        except Exception as e:
            continue

    if not engine:
        raise RuntimeError("Could not connect to database.")

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        if action == "delete":
            await delete_test_data_in_session(session)
        else:
            await seed_test_database_in_session(session)

if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "seed"
    asyncio.run(main(action))
