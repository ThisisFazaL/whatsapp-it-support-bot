import asyncio
import logging
from sqlalchemy import select
from app.database import async_session_factory, Employee, SupportAdmin, Department, Location
from app.workshop.models import WorkshopStaff

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sync_directory")

async def sync():
    async with async_session_factory() as session:
        logger.info("Starting synchronization of official fleet and staff directory...")

        # -------------------------------------------------------------
        # 1. WORKSHOP STAFF (Drivers)
        # -------------------------------------------------------------
        ws_res = await session.execute(select(WorkshopStaff))
        all_ws = ws_res.scalars().all()
        ws_by_name = {w.full_name.strip().lower(): w for w in all_ws}
        ws_by_phone = {w.phone.strip(): w for w in all_ws}

        # Updates for existing drivers
        driver_phone_updates = {
            "ashley zirota": "263717719287",
            "fortune samukange": "263773870555",
            "lastern sabola": "263772567464",
        }

        for name_key, new_phone in driver_phone_updates.items():
            driver = ws_by_name.get(name_key)
            if driver:
                old_phone = driver.phone
                driver.phone = new_phone
                driver.active = True
                logger.info(f"Updated WorkshopStaff driver '{driver.full_name}': {old_phone} -> {new_phone}")
            else:
                logger.warning(f"Driver '{name_key}' not found in WorkshopStaff!")

        # Insert Nathan into WorkshopStaff if missing
        nathan = ws_by_phone.get("263772240303") or ws_by_name.get("nathan")
        if not nathan:
            nathan = WorkshopStaff(
                full_name="Nathan",
                phone="263772240303",
                role="DRIVER",
                active=True
            )
            session.add(nathan)
            logger.info("Inserted new driver 'Nathan' (263772240303) into WorkshopStaff.")
        else:
            nathan.phone = "263772240303"
            nathan.role = "DRIVER"
            nathan.active = True
            logger.info("Verified driver 'Nathan' (263772240303) in WorkshopStaff.")

        # -------------------------------------------------------------
        # 2. EMPLOYEES (Sales Reps, Admins, Accounts, Logistics)
        # -------------------------------------------------------------
        emp_res = await session.execute(select(Employee))
        all_emps = emp_res.scalars().all()
        emp_by_name = {e.full_name.strip().lower(): e for e in all_emps}
        emp_by_phone = {e.phone.strip(): e for e in all_emps}

        # Phone updates for existing employees
        # Mazviita Sibongile Ruzvidzo: 263718174894
        maz = emp_by_phone.get("263786673351") or emp_by_name.get("mazviita sibongile ruzvidzo")
        if maz:
            old_p = maz.phone
            maz.phone = "263718174894"
            maz.active = True
            logger.info(f"Updated Employee '{maz.full_name}': {old_p} -> 263718174894")

        # Munashe Milca: 263788068567
        milca = emp_by_phone.get("263788068560") or emp_by_name.get("milcah munashe chidemo") or emp_by_name.get("munashe milca")
        if milca:
            old_p = milca.phone
            milca.full_name = "Munashe Milca"
            milca.phone = "263788068567"
            milca.department_id = 30  # Accounts
            milca.active = True
            logger.info(f"Updated Employee to 'Munashe Milca': {old_p} -> 263788068567")

        # Mercy Mungoriwo: 263711421201
        mercy = emp_by_phone.get("263780480274") or emp_by_name.get("mercy mungoriwo")
        if mercy:
            old_p = mercy.phone
            mercy.phone = "263711421201"
            mercy.active = True
            logger.info(f"Updated Employee '{mercy.full_name}': {old_p} -> 263711421201")

        # Primrose Makumbe: 263781337103
        prim = emp_by_phone.get("263787891815") or emp_by_name.get("primrose makumbe")
        if prim:
            old_p = prim.phone
            prim.phone = "263781337103"
            prim.active = True
            logger.info(f"Updated Employee '{prim.full_name}': {old_p} -> 263781337103")

        # Stuart Chaleka: check that 263718643451 exists
        stuart = emp_by_phone.get("263718643451") or emp_by_name.get("stuart chaleka")
        if stuart:
            stuart.phone = "263718643451"
            stuart.full_name = "Stuart Chaleka"
            stuart.active = True
            logger.info(f"Verified Employee '{stuart.full_name}': 263718643451")

        # New Employees to insert if missing
        new_reps = [
            {"name": "Callistus Keche", "phone": "263777425204", "dept_id": 24}, # Lg Sales
            {"name": "Tafadzwa Chikove", "phone": "263788231069", "dept_id": 18}, # Tg Sales And Marketing
            {"name": "Mufaro Gambiza", "phone": "263783103611", "dept_id": 4},   # Sales (Kreckle)
            {"name": "Nathan", "phone": "263772240303", "dept_id": 22},           # Logistics (Driver)
        ]

        # Get default location id if available
        loc_res = await session.execute(select(Location))
        loc = loc_res.scalars().first()
        loc_id = loc.location_id if loc else None

        for nr in new_reps:
            existing = emp_by_phone.get(nr["phone"]) or emp_by_name.get(nr["name"].lower())
            if not existing:
                emp = Employee(
                    full_name=nr["name"],
                    phone=nr["phone"],
                    department_id=nr["dept_id"],
                    location_id=loc_id,
                    active=True
                )
                session.add(emp)
                logger.info(f"Inserted new Employee: {nr['name']} ({nr['phone']}, Dept {nr['dept_id']})")
            else:
                existing.phone = nr["phone"]
                existing.full_name = nr["name"]
                existing.department_id = nr["dept_id"]
                existing.active = True
                logger.info(f"Updated existing Employee: {nr['name']} ({nr['phone']})")

        # -------------------------------------------------------------
        # 3. VERIFY SUJIT PATEL
        # -------------------------------------------------------------
        sujit_admin = (await session.execute(select(SupportAdmin).where(SupportAdmin.phone.like("%718352518%")))).scalars().first()
        if sujit_admin:
            sujit_admin.is_maintenance_admin = False
            sujit_admin.is_master_admin = False
            logger.info(f"Confirmed Sujit Patel ({sujit_admin.phone}) is dedicated Fleet Admin ONLY in support_admins.")

        await session.commit()
        logger.info("Database synchronization completed successfully!")

if __name__ == "__main__":
    asyncio.run(sync())
