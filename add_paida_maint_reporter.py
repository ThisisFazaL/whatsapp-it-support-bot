import asyncio
import logging
from sqlalchemy import select, update
from app.database import async_session_factory, Employee

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("add_paida")

async def add_paida():
    phone = "263712127593"
    async with async_session_factory() as session:
        stmt = select(Employee).where(Employee.phone == phone)
        res = await session.execute(stmt)
        emp = res.scalars().first()
        
        if emp:
            emp.is_maintenance_reporter = True
            await session.commit()
            logger.info(f"✅ Updated existing employee '{emp.full_name}' ({emp.phone}) -> is_maintenance_reporter=True")
        else:
            new_emp = Employee(
                full_name="Paida",
                phone=phone,
                active=True,
                is_maintenance_reporter=True
            )
            session.add(new_emp)
            await session.commit()
            logger.info(f"✅ Created new employee 'Paida' ({phone}) -> is_maintenance_reporter=True")

if __name__ == "__main__":
    asyncio.run(add_paida())
