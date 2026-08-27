import asyncio
import logging
from sqlalchemy import select, delete, text
from app.database import (
    async_session_factory, MaintenanceTicket, MaintenanceTicketAssignment, Location
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("wipe_maint")

async def wipe_all_maint_tickets_and_sync_locations():
    logger.info("Wiping all maintenance tickets and syncing 7 project locations...")
    async with async_session_factory() as session:
        # 1. Delete all existing maintenance ticket assignments and maintenance tickets
        await session.execute(delete(MaintenanceTicketAssignment))
        await session.execute(delete(MaintenanceTicket))
        await session.commit()
        logger.info("✅ All maintenance/projects tickets wiped cleanly!")

        # Reset PostgreSQL sequence if running on Postgres
        try:
            await session.execute(text("ALTER SEQUENCE maintenance_tickets_ticket_id_seq RESTART WITH 1;"))
            await session.execute(text("ALTER SEQUENCE maintenance_ticket_assignments_assignment_id_seq RESTART WITH 1;"))
            await session.commit()
            logger.info("Reset PostgreSQL maintenance ticket sequence to 1.")
        except Exception as e:
            logger.warning(f"Sequence reset skipped: {e}")

        # 2. Sync exact 7 Locations in database
        desired_locations = [
            "Tagoneswa Hardware",
            "LG Plast",
            "Shop 5",
            "Shop 6",
            "Kreckle Foods",
            "19 Mcloughlin Kensington",
            "12 Divine Milton Park"
        ]
        res = await session.execute(select(Location).order_by(Location.location_id))
        existing_locs = res.scalars().all()
        for idx, name in enumerate(desired_locations):
            if idx < len(existing_locs):
                existing_locs[idx].location_name = name
            else:
                session.add(Location(location_name=name))
        await session.commit()
        logger.info("✅ Synced 7 Project Site Locations in database!")

async def cleanup_and_renumber():
    await wipe_all_maint_tickets_and_sync_locations()

if __name__ == "__main__":
    asyncio.run(wipe_all_maint_tickets_and_sync_locations())
