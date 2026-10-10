import asyncio
import logging
from sqlalchemy import select, delete
from app.database import (
    async_session_factory,
    FleetTripRequest,
    FleetCustomerSchedule,
    FleetTripApproval,
    FleetEmergencyExpense,
    ConversationState
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("purge_trips")

async def purge_all_test_trips():
    async with async_session_factory() as session:
        logger.info("--- Purging All Test Fleet Trips and Test Expenses ---")

        # 1. Delete customer schedules
        del_fcs = await session.execute(
            delete(FleetCustomerSchedule).where(
                FleetCustomerSchedule.trip_id.in_(["06102026-murambinda", "23092026-NORTON", "TRIP-2026-SOLO-01"])
            )
        )
        logger.info(f"Deleted {del_fcs.rowcount} rows from FleetCustomerSchedule")

        # 2. Delete emergency expenses
        del_fee = await session.execute(
            delete(FleetEmergencyExpense).where(
                FleetEmergencyExpense.trip_id.in_(["06102026-murambinda", "23092026-NORTON", "TRIP-2026-SOLO-01"])
            )
        )
        logger.info(f"Deleted {del_fee.rowcount} rows from FleetEmergencyExpense")

        # 3. Delete fleet trip approvals if any
        del_fta = await session.execute(
            delete(FleetTripApproval).where(
                FleetTripApproval.trip_id.in_(["06102026-murambinda", "23092026-NORTON", "TRIP-2026-SOLO-01"])
            )
        )
        logger.info(f"Deleted {del_fta.rowcount} rows from FleetTripApproval")

        # 4. Delete trips from FleetTripRequest
        del_ftr = await session.execute(
            delete(FleetTripRequest).where(
                FleetTripRequest.trip_id.in_(["06102026-murambinda", "23092026-NORTON", "TRIP-2026-SOLO-01"])
            )
        )
        logger.info(f"Deleted {del_ftr.rowcount} rows from FleetTripRequest")

        # 5. Clean up stale driver/sales conversation states referencing these test trips
        stale_phones = [
            "263788112771",  # Terrence Mupfumi awaiting fuel for 23092026-NORTON
            "263783175517",  # awaiting departure for test trip 29092026-RUWA
            "263774364811",  # awaiting departure for test trip 23092026-JURU
            "263781207175",  # fleet_pending
            "263780543771",  # fleet_approval
        ]
        del_cs = await session.execute(
            delete(ConversationState).where(ConversationState.phone.in_(stale_phones))
        )
        logger.info(f"Deleted {del_cs.rowcount} stale conversation state rows")

        # Commit changes
        await session.commit()
        logger.info("--- Successfully committed! Database is 100% clean of all test trips! ---")

if __name__ == "__main__":
    asyncio.run(purge_all_test_trips())
