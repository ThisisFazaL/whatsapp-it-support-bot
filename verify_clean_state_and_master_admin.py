import asyncio
import logging
from unittest.mock import patch, AsyncMock
from sqlalchemy import select
from app.config import settings
from app.database import (
    async_session_factory, FleetTripRequest, FleetCustomerSchedule, FleetTripApproval,
    FleetEmergencyExpense, FleetPendingLedger, SalesRepPayment, SupportAdmin, Employee,
    ConversationState, Ticket
)
from app.workshop.models import WorkshopStaff
from app.workshop.router import get_workshop_staff
from app.state_manager import is_admin, get_user_state
from app.handlers.fleet_approval_handler import is_salesperson, get_effective_tester_role, get_solo_test_mode
from app.handlers.logistics_handler import is_edward
from app.handlers.admin_handler import handle_admin_command

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_verify")

async def test_verification():
    logger.info("=== STEP 1: VERIFYING DATABASE TEST DATA REMOVAL ===")
    async with async_session_factory() as session:
        # 1. Test trips
        all_trips = (await session.execute(select(FleetTripRequest))).scalars().all()
        assert len(all_trips) == 0, f"Expected 0 trips remaining, found {len(all_trips)}"
        logger.info("PASSED: All test fleet trips (Murambinda, Norton, Solo) completely purged (Total: 0).")

        # 2. Test emergency expenses
        all_expenses = (await session.execute(select(FleetEmergencyExpense))).scalars().all()
        assert len(all_expenses) == 0, f"Expected 0 expenses remaining, found {len(all_expenses)}"
        logger.info("PASSED: All test emergency expenses completely purged (Total: 0).")

        # 3. Test pending ledger
        test_ledgers = (await session.execute(select(FleetPendingLedger))).scalars().all()
        assert len(test_ledgers) == 0, f"Expected 0 test ledgers, found {len(test_ledgers)}"
        logger.info("PASSED: Test pending ledgers #43-46 completely purged.")

        # 4. Test payments
        test_pmts = (await session.execute(select(SalesRepPayment))).scalars().all()
        assert len(test_pmts) == 0, f"Expected 0 test payments, found {len(test_pmts)}"
        logger.info("PASSED: Test payments #14-15 completely purged.")

        # 5. WorkshopStaff for Fazal
        ws_user = await get_workshop_staff(session, "919265368695")
        assert ws_user is None, f"Expected Fazal not in WorkshopStaff, found {ws_user}"
        logger.info("PASSED: Fazal is NOT in WorkshopStaff (no driver role).")

        # 6. Mock admins
        mock_adms = (await session.execute(
            select(SupportAdmin).where(SupportAdmin.admin_id.in_([2, 3]))
        )).scalars().all()
        assert len(mock_adms) == 0, f"Expected 0 mock admins, found {len(mock_adms)}"
        logger.info("PASSED: Mock admins Alex Rivera & Sarah Jenkins purged.")

        # 7. Mock employees
        mock_emps = (await session.execute(
            select(Employee).where(Employee.employee_id.in_([76, 106]))
        )).scalars().all()
        assert len(mock_emps) == 0, f"Expected 0 mock employees, found {len(mock_emps)}"
        logger.info("PASSED: Mock employees Test Salesperson & Test Rep purged.")

        # 8. Real data preservation
        it_tkts = (await session.execute(select(Ticket))).scalars().all()
        assert len(it_tkts) == 103, f"Expected 103 real IT tickets preserved, found {len(it_tkts)}"
        logger.info(f"PASSED: Real IT tickets preserved (Total: {len(it_tkts)}).")

        logger.info("=== STEP 2: VERIFYING MASTER ADMIN CONFIG & ROLES ===")
        # Check Fazal in SupportAdmin
        fazal_admin = await is_admin(session, "919265368695")
        assert fazal_admin is not None, "Fazal must exist in SupportAdmin"
        assert fazal_admin.is_master_admin is True, "Fazal must be Master Admin"
        assert fazal_admin.active is True, "Fazal must be active"
        logger.info(f"PASSED: SupportAdmin Fazal Saiyed: Master Admin={fazal_admin.is_master_admin}, Active={fazal_admin.active}")

        # Check config settings
        assert settings.master_admin_phone == "919265368695", "Master admin phone must be 919265368695"
        assert settings.test_user_role == "MASTER_ADMIN", f"Expected MASTER_ADMIN, got {settings.test_user_role}"
        assert settings.solo_test_mode is False, "Solo test mode must be False"
        assert "919265368695" not in settings.accounts_phones, "Fazal must not be in accounts_phones"
        assert get_solo_test_mode() is False, "get_solo_test_mode() must be False"
        assert get_effective_tester_role("919265368695") == "MASTER_ADMIN", "Effective role must be MASTER_ADMIN"
        assert not await is_salesperson(session, "919265368695"), "Fazal must NOT be salesperson"
        assert not is_edward("919265368695"), "Fazal must NOT be Edward"
        logger.info("PASSED: All role helper checks verify Fazal is strictly MASTER ADMIN ONLY.")

        logger.info("=== STEP 3: VERIFYING CONVERSATION STATE ===")
        cs = await get_user_state(session, "919265368695")
        assert cs is not None, "Conversation state must exist for Fazal"
        assert cs.flow_name == "admin", f"Expected flow_name='admin', got {cs.flow_name}"
        assert cs.current_step == "admin_portal", f"Expected current_step='admin_portal', got {cs.current_step}"
        logger.info(f"PASSED: ConversationState for Fazal: flow={cs.flow_name}, step={cs.current_step}, data={cs.current_data}")

        logger.info("=== STEP 4: SIMULATING MASTER ADMIN GREETING & MENU FLOW ===")
        with patch("app.handlers.admin_handler.meta_api.send_button_message", new_callable=AsyncMock) as mock_send_btn:
            handled = await handle_admin_command(session, "919265368695", "hi")
            assert handled is True, "handle_admin_command must handle 'hi'"
            mock_send_btn.assert_called_once()
            call_kwargs = mock_send_btn.call_args.kwargs
            assert call_kwargs["to_phone"] == "919265368695"
            assert "SUPPORT ADMIN PORTAL" in call_kwargs["header_text"]
            assert "Fazal Saiyed" in call_kwargs["body_text"]
            btn_ids = [b["id"] for b in call_kwargs["buttons"]]
            assert "cmd_my_assigned_tickets" in btn_ids
            assert "cmd_unassigned_tickets" in btn_ids
            assert "cmd_raise_ticket" in btn_ids
            logger.info("PASSED: Master Admin portal greeting successfully returned correct 3 buttons.")

    logger.info("=====================================================")
    logger.info("🎉 ALL TESTS PASSED! DATABASE & ROLES ARE 100% READY!")
    logger.info("=====================================================")

if __name__ == "__main__":
    asyncio.run(test_verification())
