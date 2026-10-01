import asyncio
import unittest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from sqlalchemy import select

from app.database import (
    async_session_factory,
    init_db_models,
    AuditLog,
    FleetPendingLedger,
    SalesRepPayment,
    WebUser,
    UserCustomPermission
)
from app.auth import (
    ALL_PERMISSIONS,
    ROLE_DEFAULT_PERMISSIONS,
    user_has_permission,
    get_effective_permissions,
    require_permission,
    set_user_custom_permission,
    USER_CUSTOM_PERMISSIONS_CACHE
)
from app.dashboard import (
    api_update_fuel,
    api_update_city_min,
    api_update_meal_rate,
    api_update_accommodation_rate,
    api_clear_sales_rep_payment,
    api_get_users,
    api_save_user,
    api_toggle_user_permission,
    api_save_truck,
    api_save_driver,
    api_save_sales_rep,
    dashboard_view,
    get_dashboard_data
)


class TestRBACAndGovernance(unittest.IsolatedAsyncioTestCase):
    """
    Authoritative test suite for TAGONESWA Architecture Contract v2.3.0:
    - 9 Roles with strict default permission boundaries.
    - User-level custom permission override delegation engine (without hardcoding usernames).
    - Sujit (FLEET_ADMIN + 4 explicit custom permissions) authorization verification.
    - SALES_ADMIN strict lockdown against commercial rates & debt clearance.
    - ACCOUNTS_USER default denial on debt clearance.
    - EXECUTIVE_OBSERVER read-only isolation.
    - Debt over-clearance protection & double-entry ledger offset.
    - User management APIs with audit trail.
    """

    async def asyncSetUp(self):
        await init_db_models()

    def make_mock_request(self, json_data: dict, headers: dict = None):
        req = MagicMock()
        async def json_coro():
            return json_data
        req.json = json_coro
        req.headers = headers or {"x-forwarded-for": "127.0.0.1"}
        req.client = MagicMock()
        req.client.host = "127.0.0.1"
        return req

    # -------------------------------------------------------------
    # 1. MASTER_ADMIN Full Access Verification
    # -------------------------------------------------------------
    def test_master_admin_has_all_permissions(self):
        master = {"username": "admin", "role": "MASTER_ADMIN", "custom_permissions": {}}
        for p in ALL_PERMISSIONS:
            self.assertTrue(user_has_permission(master, p), f"MASTER_ADMIN should have {p}")

    @patch("app.dashboard.get_current_user_from_request", return_value={"name": "Super Admin", "username": "admin", "role": "MASTER_ADMIN", "custom_permissions": {}})
    async def test_master_admin_can_update_fuel_and_rates(self, mock_user):
        req_fuel = self.make_mock_request({"fuel_price": 1.70, "recalculate_cities": False})
        async with async_session_factory() as session:
            res_fuel = await api_update_fuel(req_fuel, session)
            self.assertEqual(res_fuel["status"], "success")

        req_meal = self.make_mock_request({"meal_rate_usd": 3.00, "reason": "Test adjustment"})
        async with async_session_factory() as session:
            res_meal = await api_update_meal_rate(req_meal, session)
            self.assertEqual(res_meal["status"], "success")
            self.assertEqual(res_meal["meal_rate_usd"], 3.00)
            # Cleanup
            await api_update_fuel(self.make_mock_request({"fuel_price": 1.65}), session)
            await api_update_meal_rate(self.make_mock_request({"meal_rate_usd": 2.00}), session)

    # -------------------------------------------------------------
    # 2. Base FLEET_ADMIN vs Delegated FLEET_ADMIN (Sujit)
    # -------------------------------------------------------------
    def test_base_fleet_admin_permissions(self):
        base_fleet = {"username": "fleet", "role": "FLEET_ADMIN", "custom_permissions": {}}
        # Allowed defaults
        self.assertTrue(user_has_permission(base_fleet, "manage_fuel_price"))
        self.assertTrue(user_has_permission(base_fleet, "manage_trucks"))
        self.assertTrue(user_has_permission(base_fleet, "manage_drivers"))
        self.assertTrue(user_has_permission(base_fleet, "view_audit_logs"))

        # Denied defaults (require explicit delegation)
        self.assertFalse(user_has_permission(base_fleet, "manage_city_minimums"))
        self.assertFalse(user_has_permission(base_fleet, "clear_sales_rep_debt"))
        self.assertFalse(user_has_permission(base_fleet, "manage_meal_rate"))
        self.assertFalse(user_has_permission(base_fleet, "manage_accommodation_rate"))
        self.assertFalse(user_has_permission(base_fleet, "manage_user_permissions"))

    @patch("app.dashboard.get_current_user_from_request", return_value={"name": "Standard Fleet", "username": "fleet", "role": "FLEET_ADMIN", "custom_permissions": {}})
    async def test_base_fleet_admin_denied_on_delegated_controls(self, mock_user):
        req = self.make_mock_request({"city_key": "bulawayo", "min_sales": 2500, "van_min": 1800})
        async with async_session_factory() as session:
            with self.assertRaises(HTTPException) as ctx:
                await api_update_city_min(req, session)
            self.assertEqual(ctx.exception.status_code, 403)
            self.assertIn("manage_city_minimums", str(ctx.exception.detail))

        req_clear = self.make_mock_request({
            "salesperson_phone": "263772111222",
            "salesperson_name": "Panashe",
            "cleared_amount": 50.0
        })
        async with async_session_factory() as session:
            with self.assertRaises(HTTPException) as ctx:
                await api_clear_sales_rep_payment(req_clear, session)
            self.assertEqual(ctx.exception.status_code, 403)
            self.assertIn("clear_sales_rep_debt", str(ctx.exception.detail))

    def test_delegated_sujit_permissions(self):
        # Sujit is FLEET_ADMIN + 4 explicit custom overrides
        sujit = {
            "username": "sujit",
            "role": "FLEET_ADMIN",
            "custom_permissions": {
                "manage_city_minimums": True,
                "clear_sales_rep_debt": True,
                "manage_meal_rate": True,
                "manage_accommodation_rate": True
            }
        }
        # Inherited
        self.assertTrue(user_has_permission(sujit, "manage_fuel_price"))
        self.assertTrue(user_has_permission(sujit, "manage_trucks"))
        # Delegated
        self.assertTrue(user_has_permission(sujit, "manage_city_minimums"))
        self.assertTrue(user_has_permission(sujit, "clear_sales_rep_debt"))
        self.assertTrue(user_has_permission(sujit, "manage_meal_rate"))
        self.assertTrue(user_has_permission(sujit, "manage_accommodation_rate"))
        # Denied
        self.assertFalse(user_has_permission(sujit, "manage_user_permissions"))

    @patch("app.dashboard.get_current_user_from_request", return_value={
        "name": "Sujit (Fleet Admin)",
        "username": "sujit",
        "role": "FLEET_ADMIN",
        "custom_permissions": {
            "manage_city_minimums": True,
            "clear_sales_rep_debt": True,
            "manage_meal_rate": True,
            "manage_accommodation_rate": True
        }
    })
    async def test_sujit_can_execute_delegated_mutations(self, mock_user):
        req_city = self.make_mock_request({"city_key": "mutare", "min_sales": 1600.0, "van_min": 1200.0})
        async with async_session_factory() as session:
            res_city = await api_update_city_min(req_city, session)
            self.assertEqual(res_city["status"], "success")

        req_meal = self.make_mock_request({"meal_rate_usd": 2.50, "reason": "Sujit approval"})
        async with async_session_factory() as session:
            res_meal = await api_update_meal_rate(req_meal, session)
            self.assertEqual(res_meal["status"], "success")
            self.assertEqual(res_meal["meal_rate_usd"], 2.50)
            # Cleanup
            await api_update_meal_rate(self.make_mock_request({"meal_rate_usd": 2.00, "reason": "Cleanup"}), session)

    # -------------------------------------------------------------
    # 3. SALES_ADMIN Strict Lockdown
    # -------------------------------------------------------------
    @patch("app.dashboard.get_current_user_from_request", return_value={"name": "Sales Lead", "username": "sales", "role": "SALES_ADMIN", "custom_permissions": {}})
    async def test_sales_admin_forbidden_from_all_pricing_and_debt_clearance(self, mock_user):
        async with async_session_factory() as session:
            # 1. Fuel price
            with self.assertRaises(HTTPException) as ctx:
                await api_update_fuel(self.make_mock_request({"fuel_price": 2.0}), session)
            self.assertEqual(ctx.exception.status_code, 403)

            # 2. City minimum
            with self.assertRaises(HTTPException) as ctx:
                await api_update_city_min(self.make_mock_request({"city_key": "gweru", "min_sales": 2000.0}), session)
            self.assertEqual(ctx.exception.status_code, 403)

            # 3. Meal rate
            with self.assertRaises(HTTPException) as ctx:
                await api_update_meal_rate(self.make_mock_request({"meal_rate_usd": 2.50}), session)
            self.assertEqual(ctx.exception.status_code, 403)

            # 4. Accommodation rate
            with self.assertRaises(HTTPException) as ctx:
                await api_update_accommodation_rate(self.make_mock_request({"accommodation_rate_usd": 20.0}), session)
            self.assertEqual(ctx.exception.status_code, 403)

            # 5. Clear debt
            with self.assertRaises(HTTPException) as ctx:
                await api_clear_sales_rep_payment(self.make_mock_request({"salesperson_phone": "263772111222", "cleared_amount": 50.0}), session)
            self.assertEqual(ctx.exception.status_code, 403)

            # 6. User management
            with self.assertRaises(HTTPException) as ctx:
                await api_get_users(self.make_mock_request({}), session)
            self.assertEqual(ctx.exception.status_code, 403)

    # -------------------------------------------------------------
    # 4. ACCOUNTS_USER Default Denial on Debt Clearance
    # -------------------------------------------------------------
    @patch("app.dashboard.get_current_user_from_request", return_value={"name": "Accounts Lead", "username": "accounts", "role": "ACCOUNTS_USER", "custom_permissions": {}})
    async def test_accounts_user_denied_debt_clearance_by_default(self, mock_user):
        req = self.make_mock_request({"salesperson_phone": "263772111222", "cleared_amount": 50.0})
        async with async_session_factory() as session:
            with self.assertRaises(HTTPException) as ctx:
                await api_clear_sales_rep_payment(req, session)
            self.assertEqual(ctx.exception.status_code, 403)
            self.assertIn("clear_sales_rep_debt", str(ctx.exception.detail))

    # -------------------------------------------------------------
    # 5. EXECUTIVE_OBSERVER Read-Only Lockdown
    # -------------------------------------------------------------
    @patch("app.dashboard.get_current_user_from_request", return_value={"name": "Executive Observer", "username": "executive", "role": "EXECUTIVE_OBSERVER", "custom_permissions": {}})
    async def test_executive_observer_denied_on_mutations(self, mock_user):
        async with async_session_factory() as session:
            with self.assertRaises(HTTPException) as ctx:
                await api_update_fuel(self.make_mock_request({"fuel_price": 1.8}), session)
            self.assertEqual(ctx.exception.status_code, 403)

            with self.assertRaises(HTTPException) as ctx:
                await api_save_truck(self.make_mock_request({"truck_number": "T-01", "plate_number": "AFZ 001"}), session)
            self.assertEqual(ctx.exception.status_code, 403)

    # -------------------------------------------------------------
    # 6. Debt Over-Clearance Protection & Ledger Verification
    # -------------------------------------------------------------
    @patch("app.dashboard.get_current_user_from_request", return_value={"name": "Super Admin", "username": "admin", "role": "MASTER_ADMIN", "custom_permissions": {}})
    async def test_debt_over_clearance_protection(self, mock_user):
        import time
        test_phone = f"26377{int(time.time() * 1000) % 1000000:06d}"
        # Seed $50 debt
        async with async_session_factory() as session:
            debt = FleetPendingLedger(
                salesperson_phone=test_phone,
                salesperson_name="Test Rep",
                entry_type="UNRECOVERED_SHORTFALL",
                amount=50.00,
                notes="Seed debt"
            )
            session.add(debt)
            await session.commit()

        # Attempt to clear negative or zero amount
        async with async_session_factory() as session:
            req_zero = self.make_mock_request({"salesperson_phone": test_phone, "cleared_amount": 0.0})
            with self.assertRaises(HTTPException) as ctx:
                await api_clear_sales_rep_payment(req_zero, session)
            self.assertEqual(ctx.exception.status_code, 400)

        # Attempt to clear $100 against $50 debt (over-clearance)
        async with async_session_factory() as session:
            req_over = self.make_mock_request({"salesperson_phone": test_phone, "cleared_amount": 100.0})
            with self.assertRaises(HTTPException) as ctx:
                await api_clear_sales_rep_payment(req_over, session)
            self.assertEqual(ctx.exception.status_code, 400)
            self.assertIn("cannot exceed current debt", str(ctx.exception.detail))

        # Clear valid $30 amount
        async with async_session_factory() as session:
            req_valid = self.make_mock_request({
                "salesperson_phone": test_phone,
                "salesperson_name": "Test Rep",
                "cleared_amount": 30.00,
                "payment_method": "CASH_USD",
                "reference_number": "REC-777",
                "remarks": "Partial payment"
            })
            res = await api_clear_sales_rep_payment(req_valid, session)
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["cleared_amount"], 30.00)
            self.assertEqual(res["remaining_balance"], 20.00)

        # Verify audit log includes permission_used
        async with async_session_factory() as session:
            stmt = select(AuditLog).where(AuditLog.module == "FINANCE", AuditLog.entity_id == test_phone)
            audit = (await session.execute(stmt)).scalars().first()
            self.assertIsNotNone(audit)
            self.assertEqual(audit.action, "CLEAR_SALES_REP_DEBT")
            self.assertEqual(audit.permission_used, "clear_sales_rep_debt")

    # -------------------------------------------------------------
    # 7. User Management APIs & Dynamic Grant/Revocation Engine
    # -------------------------------------------------------------
    @patch("app.dashboard.get_current_user_from_request", return_value={"name": "Super Admin", "username": "admin", "role": "MASTER_ADMIN", "custom_permissions": {}})
    async def test_user_management_grant_and_revoke_flow(self, mock_user):
        async with async_session_factory() as session:
            # 1. Fetch user list
            req_list = self.make_mock_request({})
            users_res = await api_get_users(req_list, session)
            self.assertEqual(users_res["status"], "success")
            self.assertTrue(len(users_res["users"]) > 0)

            # 2. Create test user via api_save_user
            test_username = "test_custom_user"
            save_user_req = self.make_mock_request({
                "username": test_username,
                "full_name": "Test Custom User",
                "role": "FLEET_ADMIN",
                "is_active": True,
                "reason": "Creating test user for delegation flow"
            })
            save_user_res = await api_save_user(save_user_req, session)
            self.assertEqual(save_user_res["status"], "success")

            # 3. Grant custom permission to the test user
            grant_req = self.make_mock_request({
                "username": test_username,
                "permission_key": "manage_city_minimums",
                "is_granted": True,
                "reason": "Temporary delegation for testing"
            })
            grant_res = await api_toggle_user_permission(grant_req, session)
            self.assertEqual(grant_res["status"], "success")
            self.assertTrue(grant_res["is_granted"])
            self.assertIn("manage_city_minimums", grant_res["effective_permissions"])

            # Verify in-memory cache updated
            self.assertTrue(USER_CUSTOM_PERMISSIONS_CACHE.get(test_username, {}).get("manage_city_minimums"))

            # 3. Revoke custom permission
            revoke_req = self.make_mock_request({
                "username": test_username,
                "permission_key": "manage_city_minimums",
                "is_granted": False,
                "reason": "Revocation after test completion"
            })
            revoke_res = await api_toggle_user_permission(revoke_req, session)
            self.assertEqual(revoke_res["status"], "success")
            self.assertFalse(revoke_res["is_granted"])
            self.assertNotIn("manage_city_minimums", revoke_res["effective_permissions"])

    # -------------------------------------------------------------
    # 8. Analytics Visibility Strictly Restricted to MASTER_ADMIN
    # -------------------------------------------------------------
    async def test_analytics_restricted_to_master_admin_only(self):
        # 1. Master Admin gets analytics in HTML & JSON API
        master_user = {"name": "Master", "username": "master", "role": "MASTER_ADMIN", "allowed_domains": ["fleet"], "custom_permissions": {}}
        with patch("app.dashboard.get_current_user_from_request", return_value=master_user):
            req = self.make_mock_request({})
            html_resp = await dashboard_view(req)
            self.assertIn('id="fleet-section-analytics"', html_resp.body.decode())
            self.assertIn('id="fleet-btn-analytics"', html_resp.body.decode())
            
            async with async_session_factory() as session:
                api_data = await get_dashboard_data(req, session)
                fleet_data = api_data.get("fleet", {})
                self.assertIn("analytics", fleet_data)
                self.assertNotEqual(fleet_data["analytics"], {})

        # 2. Sales Admin is denied analytics in HTML & JSON API
        sales_admin_user = {"name": "Sales Admin", "username": "everjoy", "role": "SALES_ADMIN", "allowed_domains": ["fleet"], "custom_permissions": {}}
        with patch("app.dashboard.get_current_user_from_request", return_value=sales_admin_user):
            req = self.make_mock_request({})
            html_resp = await dashboard_view(req)
            self.assertNotIn('id="fleet-section-analytics"', html_resp.body.decode())
            self.assertNotIn('id="fleet-btn-analytics"', html_resp.body.decode())
            self.assertNotIn('value="analytics"', html_resp.body.decode())
            
            async with async_session_factory() as session:
                api_data = await get_dashboard_data(req, session)
                fleet_data = api_data.get("fleet", {})
                self.assertEqual(fleet_data.get("analytics"), {})

        # 3. Fleet Admin is denied analytics in HTML & JSON API
        fleet_admin_user = {"name": "Fleet Admin", "username": "sujit", "role": "FLEET_ADMIN", "allowed_domains": ["fleet"], "custom_permissions": {}}
        with patch("app.dashboard.get_current_user_from_request", return_value=fleet_admin_user):
            req = self.make_mock_request({})
            html_resp = await dashboard_view(req)
            self.assertNotIn('id="fleet-section-analytics"', html_resp.body.decode())
            self.assertNotIn('id="fleet-btn-analytics"', html_resp.body.decode())
            
            async with async_session_factory() as session:
                api_data = await get_dashboard_data(req, session)
                fleet_data = api_data.get("fleet", {})
                self.assertEqual(fleet_data.get("analytics"), {})


if __name__ == "__main__":
    unittest.main()
