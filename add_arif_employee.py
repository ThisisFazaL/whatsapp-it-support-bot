import asyncio
import logging
from sqlalchemy import select
from app.database import async_session_factory, Department, Location, Employee

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("add_arif")

async def add_employee_arif():
    async with async_session_factory() as session:
        # 1. Ensure CEO Department exists
        stmt_dept = select(Department).where(Department.department_name == "CEO")
        dept = (await session.execute(stmt_dept)).scalars().first()
        if not dept:
            dept = Department(department_name="CEO")
            session.add(dept)
            await session.flush()
            logger.info("Created 'CEO' department.")

        # 2. Ensure Location exists
        stmt_loc = select(Location).limit(1)
        loc = (await session.execute(stmt_loc)).scalars().first()
        loc_id = loc.location_id if loc else 1

        # 3. Add or update Arif
        phone = "263732786786"
        stmt_emp = select(Employee).where(Employee.phone == phone)
        emp = (await session.execute(stmt_emp)).scalars().first()
        if not emp:
            emp = Employee(
                employee_code="EMP1005",
                full_name="Arif",
                phone=phone,
                email="arif@company.com",
                department_id=dept.department_id,
                location_id=loc_id,
                active=True
            )
            session.add(emp)
            logger.info(f"Registered new employee 'Arif' ({phone}).")
        else:
            emp.full_name = "Arif"
            emp.department_id = dept.department_id
            emp.active = True
            logger.info(f"Updated employee 'Arif' ({phone}).")

        await session.commit()
    logger.info("✅ Employee Arif registered successfully in database!")

if __name__ == "__main__":
    asyncio.run(add_employee_arif())
