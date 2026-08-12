import asyncio
import logging
from app.database import init_db_models, async_session_factory, Category, Employee, SupportAdmin
from sqlalchemy import select

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("init_db")

async def main():
    logger.info("Initializing database tables and seed data...")
    await init_db_models()
    
    async with async_session_factory() as session:
        cats = (await session.execute(select(Category))).scalars().all()
        emps = (await session.execute(select(Employee))).scalars().all()
        admins = (await session.execute(select(SupportAdmin))).scalars().all()
        
        print("\n================ DATABASE SUMMARY ================")
        print(f"Categories Loaded: {len(cats)}")
        for c in cats:
            print(f"  - [{c.category_id}] {c.category_name}")
        
        print(f"\nEmployees Registered: {len(emps)}")
        for e in emps:
            print(f"  - [{e.employee_id}] {e.full_name} | Code: {e.employee_code} | Phone: {e.phone}")
            
        print(f"\nSupport Admins Registered: {len(admins)}")
        for a in admins:
            print(f"  - [{a.admin_id}] {a.full_name} | Phone: {a.phone}")
        print("===================================================\n")
        print("==> Database ready for use!")

if __name__ == "__main__":
    asyncio.run(main())
