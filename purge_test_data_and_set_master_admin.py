import asyncio
import logging
from sqlalchemy import select, delete
from app.database import (
    async_session_factory,
    FleetTripRequest,
    FleetCustomerSchedule,
    FleetTripApproval,
    FleetEmergencyExpense,
    FleetPendingLedger,
    SalesRepPayment,
    SupportAdmin,
    Employee,
    ConversationState,
    WebUser,
    UserCustomPermission
)
from app.workshop.models import WorkshopStaff
from app.state_manager import invalidate_user_cache

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("db_purge")

async def run_purge():
    async with async_session_factory() as session:
        logger.info("--- Starting Database Purge of Test Data & Setting Master Admin ---")

        # 1. Purge test trip from FleetTripRequest
        del_ftr = await session.execute(
            delete(FleetTripRequest).where(FleetTripRequest.trip_id == "TRIP-2026-SOLO-01")
        )
        logger.info(f"Deleted {del_ftr.rowcount} test rows from FleetTripRequest (TRIP-2026-SOLO-01)")

        # 2. Purge test trip customer schedules & approvals
        del_fcs = await session.execute(
            delete(FleetCustomerSchedule).where(FleetCustomerSchedule.trip_id == "TRIP-2026-SOLO-01")
        )
        logger.info(f"Deleted {del_fcs.rowcount} rows from FleetCustomerSchedule")

        del_fta = await session.execute(
            delete(FleetTripApproval).where(FleetTripApproval.trip_id == "TRIP-2026-SOLO-01")
        )
        logger.info(f"Deleted {del_fta.rowcount} rows from FleetTripApproval")

        # 3. Purge test emergency expense
        del_fee = await session.execute(
            delete(FleetEmergencyExpense).where(
                (FleetEmergencyExpense.id == 8) | (FleetEmergencyExpense.trip_id == "TRIP-2026-SOLO-01")
            )
        )
        logger.info(f"Deleted {del_fee.rowcount} test rows from FleetEmergencyExpense")

        # 4. Purge test pending ledgers (entries 43, 44, 45, 46)
        del_fpl = await session.execute(
            delete(FleetPendingLedger).where(FleetPendingLedger.id.in_([43, 44, 45, 46]))
        )
        logger.info(f"Deleted {del_fpl.rowcount} test rows from FleetPendingLedger")

        # 5. Purge test sales rep payments (entries 14, 15)
        del_srp = await session.execute(
            delete(SalesRepPayment).where(SalesRepPayment.id.in_([14, 15]))
        )
        logger.info(f"Deleted {del_srp.rowcount} test rows from SalesRepPayment")

        # 6. Remove Fazal Saiyed from WorkshopStaff (he was mistakenly registered as DRIVER)
        del_ws = await session.execute(
            delete(WorkshopStaff).where(WorkshopStaff.phone == "919265368695")
        )
        logger.info(f"Deleted {del_ws.rowcount} driver row(s) for Fazal Saiyed from WorkshopStaff")

        # 7. Remove mock admins (Alex Rivera #2, Sarah Jenkins #3)
        del_adm = await session.execute(
            delete(SupportAdmin).where(SupportAdmin.admin_id.in_([2, 3]))
        )
        logger.info(f"Deleted {del_adm.rowcount} mock admin rows from SupportAdmin (Alex Rivera & Sarah Jenkins)")

        # 8. Ensure Fazal Saiyed in SupportAdmin is strictly Master Admin & Active
        fazal_adm_res = await session.execute(
            select(SupportAdmin).where(SupportAdmin.phone == "919265368695")
        )
        fazal_adm = fazal_adm_res.scalars().first()
        if fazal_adm:
            fazal_adm.is_master_admin = True
            fazal_adm.active = True
            fazal_adm.full_name = "Fazal Saiyed (Master Admin)"
            logger.info(f"SupportAdmin Fazal: ID={fazal_adm.admin_id}, is_master={fazal_adm.is_master_admin}, active={fazal_adm.active}")
        else:
            session.add(SupportAdmin(
                full_name="Fazal Saiyed (Master Admin)",
                phone="919265368695",
                is_master_admin=True,
                active=True
            ))
            logger.info("Created SupportAdmin row for Fazal Saiyed (Master Admin)")

        # 9. Remove mock employees (Test Salesperson #76, Test Rep #106)
        del_emp = await session.execute(
            delete(Employee).where(Employee.employee_id.in_([76, 106]))
        )
        logger.info(f"Deleted {del_emp.rowcount} mock employee rows from Employee (Test Salesperson, Test Rep)")

        # 10. Clean up test WebUser
        test_user = (await session.execute(
            select(WebUser).where(WebUser.username == "test_custom_user")
        )).scalars().first()
        if test_user:
            await session.execute(
                delete(UserCustomPermission).where(UserCustomPermission.user_id == test_user.id)
            )
            await session.execute(
                delete(WebUser).where(WebUser.id == test_user.id)
            )
            logger.info("Deleted test_custom_user and associated custom permissions from WebUser")

        # 11. Purge test conversation states & convert Fazal to Master Admin state
        del_cs_test = await session.execute(
            delete(ConversationState).where(ConversationState.phone.in_(["263771112233", "919876543222"]))
        )
        logger.info(f"Deleted {del_cs_test.rowcount} mock conversation state rows")

        # Convert Fazal's conversation state to master admin
        fazal_cs_res = await session.execute(
            select(ConversationState).where(ConversationState.phone == "919265368695")
        )
        fazal_cs = fazal_cs_res.scalars().first()
        if fazal_cs:
            fazal_cs.flow_name = "admin"
            fazal_cs.current_step = "admin_portal"
            fazal_cs.current_data = {"role": "MASTER_ADMIN", "admin_name": "Fazal Saiyed"}
            logger.info("Updated Fazal conversation state to flow='admin', step='admin_portal'")
        else:
            session.add(ConversationState(
                phone="919265368695",
                flow_name="admin",
                current_step="admin_portal",
                current_data={"role": "MASTER_ADMIN", "admin_name": "Fazal Saiyed"}
            ))
            logger.info("Created Fazal conversation state row as Master Admin")

        # Invalidate in-memory caches
        invalidate_user_cache("919265368695")
        invalidate_user_cache("+919265368695")

        await session.commit()
        logger.info("--- Transaction successfully committed! All test data purged! ---")

if __name__ == "__main__":
    asyncio.run(run_purge())
