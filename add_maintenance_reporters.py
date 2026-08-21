import asyncio
import logging
from sqlalchemy import select, text
from app.database import async_session_factory, Employee, Department, Location, engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("add_maint_reporters")

async def update_reporters():
    maint_reporters = [
        {"name": "Fazal Saiyed", "phone": "919265368695"},
        {"name": "Arif", "phone": "263732786786"},
        {"name": "Zayn", "phone": "263713866223"},
        {"name": "Faizan Patel", "phone": "263778405964"},
        {"name": "Kevin Chikati", "phone": "263718627526"}
    ]

    async with async_session_factory() as session:
        for rep in maint_reporters:
            phone = rep["phone"]
            name = rep["name"]

            stmt = select(Employee).where(Employee.phone == phone)
            emp = (await session.execute(stmt)).scalars().first()
            if emp:
                emp.is_maintenance_reporter = True
                emp.active = True
                if not emp.full_name or emp.full_name == "Staff User":
                    emp.full_name = name
                logger.info(f"Updated '{name}' ({phone}) -> is_maintenance_reporter = True")
            else:
                emp_code = f"EMP_MNT_{phone[-4:]}"
                emp = Employee(
                    employee_code=emp_code,
                    full_name=name,
                    phone=phone,
                    is_maintenance_reporter=True,
                    active=True
                )
                session.add(emp)
                logger.info(f"Created '{name}' ({phone}) -> is_maintenance_reporter = True")
        
        await session.commit()
    logger.info("✅ Maintenance reporters updated successfully!")

if __name__ == "__main__":
    asyncio.run(update_reporters())
