import asyncio
import logging
from sqlalchemy import select
from app.database import async_session_factory, Employee, Department, Location, SupportAdmin

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("add_admin_employees")

ADMIN_PROFILES = [
    {
        "name": "Kevin Chikati",
        "phone": "263718627526"
    },
    {
        "name": "Ellias Murenga",
        "phone": "263788843579"
    },
    {
        "name": "Faisal Kassim",
        "phone": "263780100503"
    }
]

async def register_admins_as_employees():
    async with async_session_factory() as session:
        # Check / create IT Support Department
        dept_res = await session.execute(select(Department).where(Department.department_name.ilike("%IT Support%")))
        dept_obj = dept_res.scalars().first()
        if not dept_obj:
            dept_obj = Department(department_name="IT Support")
            session.add(dept_obj)
            await session.flush()

        # Check / create HQ Location
        loc_res = await session.execute(select(Location).where(Location.location_name.ilike("%Coventry%")))
        loc_obj = loc_res.scalars().first()
        if not loc_obj:
            loc_obj = Location(location_name="110 Coventry Road Workington")
            session.add(loc_obj)
            await session.flush()

        for prof in ADMIN_PROFILES:
            emp_res = await session.execute(select(Employee).where(Employee.phone == prof['phone']))
            emp_obj = emp_res.scalars().first()

            if emp_obj:
                emp_obj.full_name = prof['name']
                emp_obj.department_id = dept_obj.department_id
                emp_obj.location_id = loc_obj.location_id
                emp_obj.active = True
                logger.info(f"Updated Employee profile for Admin: {prof['name']} (+{prof['phone']})")
            else:
                emp_obj = Employee(
                    full_name=prof['name'],
                    phone=prof['phone'],
                    department_id=dept_obj.department_id,
                    location_id=loc_obj.location_id,
                    active=True
                )
                session.add(emp_obj)
                logger.info(f"Created Employee profile for Admin: {prof['name']} (+{prof['phone']})")

        await session.commit()
        logger.info("✅ All support admins registered in employees table!")

if __name__ == "__main__":
    asyncio.run(register_admins_as_employees())
