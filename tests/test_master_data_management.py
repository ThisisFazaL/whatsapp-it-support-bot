import asyncio
import os
import sys
import unittest
from unittest.mock import patch, AsyncMock, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_fleet.db"

from sqlalchemy import delete, select
from app.database import (
    async_session_factory, init_db_models, AuditLog, Employee, Department,
    FleetTripApproval, FleetPendingLedger, SalesRepPayment
)
from app.workshop.models import WorkshopTruck, WorkshopStaff
from app.dashboard import (
    api_update_operational_params, api_save_truck, api_save_driver, api_save_sales_rep,
    api_clear_sales_rep_payment, api_get_audit_logs
)
from app.services.config_service import (
    get_meal_rate, get_accommodation_rate, get_expense_budget_pct, get_van_minimum_surcharge,
    update_system_setting
)


class TestMasterDataManagement(unittest.IsolatedAsyncioTestCase):
    _db_initialized = False

    async def asyncSetUp(self):
        if not TestMasterDataManagement._db_initialized:
            await init_db_models()
            TestMasterDataManagement._db_initialized = True

        async with async_session_factory() as session:
            for model in [AuditLog, SalesRepPayment, FleetPendingLedger, FleetTripApproval]:
                await session.execute(delete(model))
            await session.execute(delete(WorkshopTruck).where(WorkshopTruck.truck_number == "9999"))
            await session.execute(delete(WorkshopStaff).where(WorkshopStaff.phone == "263773999888"))
            await session.execute(delete(Employee).where(Employee.phone.in_(["263773999888", "263771555666"])))
            await session.commit()

    async def asyncTearDown(self):
        async with async_session_factory() as session:
            await update_system_setting(session, "meal_rate_usd", 2.0, changed_by="TestTeardown", reason="Reset test state")
            await update_system_setting(session, "accommodation_rate_usd", 15.0, changed_by="TestTeardown", reason="Reset test state")
            await update_system_setting(session, "expense_budget_pct", 0.04, changed_by="TestTeardown", reason="Reset test state")
            await update_system_setting(session, "van_minimum_surcharge", 0.0, changed_by="TestTeardown", reason="Reset test state")
            await session.commit()

    def make_mock_request(self, json_data):
        req = MagicMock()
        req.json = AsyncMock(return_value=json_data)
        return req

    @patch("app.dashboard.get_current_user_from_request", return_value={"name": "Admin User", "role": "MASTER_ADMIN"})
    async def test_update_operational_params(self, mock_user):
        req = self.make_mock_request({
            "meal_rate": 25.0,
            "accommodation_rate": 55.0,
            "expense_budget_pct": 0.18,
            "van_minimum_surcharge": 45.0
        })
        async with async_session_factory() as session:
            res = await api_update_operational_params(req, session)
        self.assertEqual(res["status"], "success")

        # Verify cached values
        self.assertEqual(get_meal_rate(), 25.0)
        self.assertEqual(get_accommodation_rate(), 55.0)
        self.assertEqual(get_expense_budget_pct(), 0.18)
        self.assertEqual(get_van_minimum_surcharge(), 45.0)

        # Verify audit log in DB
        async with async_session_factory() as session:
            logs = (await session.execute(
                select(AuditLog).where(AuditLog.module == "CONFIG", AuditLog.action == "UPDATE_SETTING")
            )).scalars().all()
            self.assertTrue(len(logs) >= 4)
            keys = {l.entity_id for l in logs}
            self.assertIn("meal_rate_usd", keys)
            self.assertIn("accommodation_rate_usd", keys)
            self.assertIn("expense_budget_pct", keys)
            self.assertIn("van_minimum_surcharge", keys)

    @patch("app.dashboard.get_current_user_from_request", return_value={"name": "Fleet Admin", "role": "FLEET_ADMIN"})
    async def test_truck_crud_and_audit(self, mock_user):
        # 1. Create new truck
        create_req = self.make_mock_request({
            "truck_number": "9999",
            "plate_number": "AFZ 9999",
            "model_make": "Scania R500",
            "body_type": "Horse",
            "home_depot": "Bulawayo Depot",
            "active": True
        })
        async with async_session_factory() as session:
            res_create = await api_save_truck(create_req, session)
        self.assertEqual(res_create["status"], "success")
        truck_id = res_create["truck"]["truck_id"]

        # 2. Update existing truck
        update_req = self.make_mock_request({
            "truck_id": truck_id,
            "truck_number": "9999",
            "plate_number": "AFZ 9999",
            "model_make": "Scania R500 V8 Highline",
            "body_type": "Horse",
            "home_depot": "Harare Main",
            "active": False
        })
        async with async_session_factory() as session:
            res_update = await api_save_truck(update_req, session)
        self.assertEqual(res_update["status"], "success")
        self.assertEqual(res_update["truck"]["home_depot"], "Harare Main")
        self.assertFalse(res_update["truck"]["active"])

        # 3. Verify database & audit log
        async with async_session_factory() as session:
            truck = (await session.execute(
                select(WorkshopTruck).where(WorkshopTruck.truck_id == truck_id)
            )).scalars().first()
            self.assertIsNotNone(truck)
            self.assertEqual(truck.model_make, "Scania R500 V8 Highline")

            logs = (await session.execute(
                select(AuditLog).where(AuditLog.module == "FLEET_MANAGEMENT", AuditLog.entity_id == "AFZ 9999")
            )).scalars().all()
            self.assertEqual(len(logs), 2)
            self.assertTrue(any(l.action == "ADD_COMMERCIAL_TRUCK" for l in logs))
            self.assertTrue(any(l.action == "UPDATE_COMMERCIAL_TRUCK" for l in logs))

    @patch("app.dashboard.get_current_user_from_request", return_value={"name": "Logistics Manager", "role": "LOGISTICS_MANAGER"})
    async def test_driver_crud_and_sync(self, mock_user):
        # 1. Create driver
        create_req = self.make_mock_request({
            "full_name": "Milcah Munashe",
            "phone": "263773999888",
            "role": "COMMERCIAL DRIVER",
            "active": True
        })
        async with async_session_factory() as session:
            res = await api_save_driver(create_req, session)
        self.assertEqual(res["status"], "success")
        staff_id = res["driver"]["staff_id"]

        # 2. Verify WorkshopStaff and Employee created
        async with async_session_factory() as session:
            staff = (await session.execute(
                select(WorkshopStaff).where(WorkshopStaff.staff_id == staff_id)
            )).scalars().first()
            self.assertIsNotNone(staff)
            self.assertEqual(staff.full_name, "Milcah Munashe")

            emp = (await session.execute(
                select(Employee).where(Employee.phone == "263773999888")
            )).scalars().first()
            self.assertIsNotNone(emp)
            self.assertEqual(emp.full_name, "Milcah Munashe")

            # Audit log check
            log = (await session.execute(
                select(AuditLog).where(AuditLog.module == "FLEET_MANAGEMENT", AuditLog.action == "ADD_COMMERCIAL_DRIVER", AuditLog.entity_id == "263773999888")
            )).scalars().first()
            self.assertIsNotNone(log)

    @patch("app.dashboard.get_current_user_from_request", return_value={"name": "Logistics Manager", "role": "LOGISTICS_MANAGER"})
    async def test_sales_rep_crud_and_audit(self, mock_user):
        # 1. Create Sales Rep
        create_req = self.make_mock_request({
            "full_name": "Tatenda Chiwara",
            "phone": "263771555666",
            "email": "tatenda@tagoneswa.co.zw",
            "active": True
        })
        async with async_session_factory() as session:
            res = await api_save_sales_rep(create_req, session)
        self.assertEqual(res["status"], "success")
        emp_id = res["sales_rep"]["employee_id"]

        # 2. Update Sales Rep
        update_req = self.make_mock_request({
            "employee_id": emp_id,
            "full_name": "Tatenda Chiwara Senior",
            "phone": "263771555666",
            "email": "tatenda.chiwara@tagoneswa.co.zw",
            "active": True
        })
        async with async_session_factory() as session:
            res_update = await api_save_sales_rep(update_req, session)
        self.assertEqual(res_update["status"], "success")

        # 3. Check DB
        async with async_session_factory() as session:
            emp = (await session.execute(
                select(Employee).where(Employee.employee_id == emp_id)
            )).scalars().first()
            self.assertIsNotNone(emp)
            self.assertEqual(emp.full_name, "Tatenda Chiwara Senior")

            logs = (await session.execute(
                select(AuditLog).where(AuditLog.module == "SALES_MANAGEMENT", AuditLog.entity_id == "263771555666")
            )).scalars().all()
            self.assertEqual(len(logs), 2)
            self.assertTrue(any(l.action == "ADD_SALES_REP" for l in logs))
            self.assertTrue(any(l.action == "UPDATE_SALES_REP" for l in logs))

    @patch("app.dashboard.get_current_user_from_request", return_value={"name": "Zayn Accounts", "role": "ACCOUNTS_USER"})
    async def test_clear_sales_rep_payment_and_audit(self, mock_user):
        # 1. Record debt clearance
        req = self.make_mock_request({
            "salesperson_phone": "263772111222",
            "salesperson_name": "Panashe Mazai",
            "cleared_amount": 75.50,
            "payment_method": "BANK_TRANSFER",
            "reference_number": "STANBIC-98124",
            "remarks": "Full debt settlement per receipt"
        })
        async with async_session_factory() as session:
            res = await api_clear_sales_rep_payment(req, session)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["cleared_amount"], 75.50)

        # 2. Check SalesRepPayment, FleetPendingLedger offset, and AuditLog
        async with async_session_factory() as session:
            pay = (await session.execute(
                select(SalesRepPayment).where(SalesRepPayment.salesperson_phone == "263772111222")
            )).scalars().first()
            self.assertIsNotNone(pay)
            self.assertEqual(pay.cleared_amount, 75.50)
            self.assertEqual(pay.reference_number, "STANBIC-98124")

            # Double-entry ledger entry check
            ledger = (await session.execute(
                select(FleetPendingLedger).where(
                    FleetPendingLedger.salesperson_phone == "263772111222",
                    FleetPendingLedger.entry_type == "PAYMENT_CLEARED_BY_ACCOUNTS"
                )
            )).scalars().first()
            self.assertIsNotNone(ledger)
            self.assertEqual(ledger.amount, -75.50)

            # Audit log
            log = (await session.execute(
                select(AuditLog).where(AuditLog.module == "FINANCE", AuditLog.action == "CLEAR_SALES_REP_DEBT")
            )).scalars().first()
            self.assertIsNotNone(log)
            self.assertEqual(log.new_value.get("ref"), "STANBIC-98124")
            self.assertEqual(log.remarks, "Full debt settlement per receipt")

            # 3. Check api_get_audit_logs returns the record
            logs_req = self.make_mock_request({})
            logs_res = await api_get_audit_logs(logs_req, session)
            self.assertIn("logs", logs_res)
            self.assertTrue(any(l["action"] == "CLEAR_SALES_REP_DEBT" for l in logs_res["logs"]))


if __name__ == "__main__":
    unittest.main()
