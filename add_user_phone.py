import asyncio
from app.database import async_session_factory, Employee, SupportAdmin
from sqlalchemy import select

async def add_phone():
    async with async_session_factory() as session:
        # Check if already in employees
        stmt = select(Employee).where(Employee.phone == "919265368695")
        emp = (await session.execute(stmt)).scalars().first()
        if not emp:
            new_emp = Employee(
                employee_code="EMP1004",
                full_name="User",
                phone="919265368695",
                email="user@company.com",
                department_id=1,
                location_id=1,
                active=True
            )
            session.add(new_emp)
            print("Added Employee 919265368695!")
        else:
            print("Employee 919265368695 already exists!")

        # Check if in support_admins
        stmt_admin = select(SupportAdmin).where(SupportAdmin.phone == "919265368695")
        admin = (await session.execute(stmt_admin)).scalars().first()
        if not admin:
            new_admin = SupportAdmin(
                full_name="User Admin",
                phone="919265368695",
                active=True
            )
            session.add(new_admin)
            print("Added SupportAdmin 919265368695!")
        else:
            print("SupportAdmin 919265368695 already exists!")

        await session.commit()
        print("Database updated successfully!")

if __name__ == "__main__":
    asyncio.run(add_phone())
