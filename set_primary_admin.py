import asyncio
from app.database import async_session_factory, SupportAdmin
from sqlalchemy import select, update

async def set_admin():
    async with async_session_factory() as session:
        # Set only 919265368695 as active admin so all admin alerts go to your phone
        await session.execute(update(SupportAdmin).values(active=False))
        
        stmt = select(SupportAdmin).where(SupportAdmin.phone == "919265368695")
        admin = (await session.execute(stmt)).scalars().first()
        if admin:
            admin.active = True
        else:
            new_admin = SupportAdmin(full_name="Fazal (Lead Admin)", phone="919265368695", active=True)
            session.add(new_admin)
            
        await session.commit()
        print("Updated Support Admin table: Fazal (919265368695) is now the active primary admin!")

if __name__ == "__main__":
    asyncio.run(set_admin())
