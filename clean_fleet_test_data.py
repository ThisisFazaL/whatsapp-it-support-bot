import asyncio
import logging
from sqlalchemy import delete
from app.database import (
    async_session_factory,
    FleetTripRequest,
    FleetCustomerSchedule,
    FleetEmergencyExpense,
    FleetTripApproval,
    FleetPendingLedger,
    DriverPendingLedger,
    ConversationState
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("clean_fleet_test_data")


async def clean_fleet_test_data():
    """Safely cleans fleet testing data while leaving core employees and IT/maintenance data 100% untouched."""
    async with async_session_factory() as session:
        logger.info("Starting safe fleet testing data cleanup...")

        # 1. Fleet Trip Requests
        r1 = await session.execute(delete(FleetTripRequest))
        logger.info(f"Deleted {r1.rowcount} FleetTripRequest records.")

        # 2. Fleet Customer Schedules
        r2 = await session.execute(delete(FleetCustomerSchedule))
        logger.info(f"Deleted {r2.rowcount} FleetCustomerSchedule records.")

        # 3. Fleet Emergency Expenses
        r3 = await session.execute(delete(FleetEmergencyExpense))
        logger.info(f"Deleted {r3.rowcount} FleetEmergencyExpense records.")

        # 4. Fleet Trip Approvals
        r4 = await session.execute(delete(FleetTripApproval))
        logger.info(f"Deleted {r4.rowcount} FleetTripApproval records.")

        # 5. Fleet Pending Ledgers
        r5 = await session.execute(delete(FleetPendingLedger))
        logger.info(f"Deleted {r5.rowcount} FleetPendingLedger records.")

        # 6. Driver Pending Ledgers
        r6 = await session.execute(delete(DriverPendingLedger))
        logger.info(f"Deleted {r6.rowcount} DriverPendingLedger records.")

        # 7. Reset active fleet conversation states
        fleet_flows = [
            "fleet_approval", "fleet_edward", "fleet_zayn",
            "fleet_driver", "fleet_sales_admin", "fleet_logistics_manager"
        ]
        r7 = await session.execute(
            delete(ConversationState).where(ConversationState.flow_name.in_(fleet_flows))
        )
        logger.info(f"Reset {r7.rowcount} active fleet conversation states.")

        await session.commit()
        logger.info("Fleet testing data cleanup completed successfully!")


if __name__ == "__main__":
    asyncio.run(clean_fleet_test_data())
