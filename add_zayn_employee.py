import asyncio
import logging
from sqlalchemy import select
from app.database import async_session_factory, Employee, Department, Location, engine
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("add_zayn")

async def add_zayn():
    phone = "263713866223"
    name = "Zayn"
    loc_str = "110 Coventry Road Workington"
    
    logger.info(f"Adding new employee: {name} ({phone})...")
    async with async_session_factory() as session:
        # Check Location
        loc_stmt = select(Location).where(Location.location_name == loc_str)
        loc = (await session.execute(loc_stmt)).scalars().first()
        if not loc:
            loc = Location(location_name=loc_str)
            session.add(loc)
            await session.flush()

        # Check Department (default to General if missing)
        dept_stmt = select(Department).where(Department.department_name == "General")
        dept = (await session.execute(dept_stmt)).scalars().first()
        if not dept:
            dept = Department(department_name="General")
            session.add(dept)
            await session.flush()

        # Insert / Update Employee
        emp_stmt = select(Employee).where(Employee.phone == phone)
        emp = (await session.execute(emp_stmt)).scalars().first()
        if not emp:
            # Generate code EMP1061
            max_id_stmt = select(Employee.employee_id).order_by(Employee.employee_id.desc())
            max_id = (await session.execute(max_id_stmt)).scalars().first() or 1000
            emp_code = f"EMP{max_id + 1}"

            emp = Employee(
                employee_code=emp_code,
                full_name=name,
                phone=phone,
                email="zayn@company.com",
                department_id=dept.department_id,
                location_id=loc.location_id,
                active=True
            )
            session.add(emp)
            logger.info(f"Inserted new employee {name} with code {emp_code}.")
        else:
            emp.full_name = name
            emp.active = True
            logger.info(f"Updated existing employee {name}.")

        await session.commit()

    # Sync sequence
    async with engine.begin() as conn:
        try:
            await conn.execute(text("SELECT setval('employees_employee_id_seq', COALESCE((SELECT MAX(employee_id) FROM employees), 0) + 1, false);"))
        except Exception:
            pass

    logger.info(f"✅ Employee {name} ({phone}) registered successfully!")

if __name__ == "__main__":
    asyncio.run(add_zayn())
