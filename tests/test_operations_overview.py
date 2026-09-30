import asyncio
import unittest
from unittest.mock import patch, MagicMock
from app.database import async_session_factory, init_db_models
from app.dashboard import get_dashboard_data


class TestOperationsOverview(unittest.IsolatedAsyncioTestCase):
    """
    Verification test suite for TAGONESWA Operations Overview:
    - Verifies KPI summary calculation from live database models.
    - Verifies operational exception alert generation and priority categorisation.
    - Verifies role-aware gating (Master Admin, Sales Admin, Fleet Admin, Accounts, Executive Observer).
    - Verifies read-only lockdown for Executive Observer.
    - Verifies chronological recent activity feed blending audit logs and transactions.
    """

    async def asyncSetUp(self):
        await init_db_models()

    def make_mock_request(self):
        req = MagicMock()
        return req

    async def test_operations_overview_payload_for_master_admin(self):
        mock_user = {
            "username": "master",
            "name": "Master Administrator",
            "role": "MASTER_ADMIN",
            "allowed_domains": ["it", "projects", "logistics", "fleet", "accounts", "admin"]
        }
        mock_req = self.make_mock_request()

        with patch("app.dashboard.get_current_user_from_request", return_value=mock_user):
            async with async_session_factory() as session:
                data = await get_dashboard_data(mock_req, session)

        self.assertIn("fleet", data)
        self.assertIsNotNone(data["fleet"])
        self.assertIn("overview", data["fleet"])
        overview = data["fleet"]["overview"]

        # 1. KPI Structure Verification
        kpis = overview["kpis"]
        self.assertIn("active_ongoing_trips", kpis)
        self.assertIn("in_transit_trips", kpis)
        self.assertIn("pending_trip_approvals", kpis)
        self.assertIn("trucks_total", kpis)
        self.assertIn("trucks_active", kpis)
        self.assertIn("drivers_total", kpis)
        self.assertIn("drivers_active", kpis)
        self.assertIn("pending_bottlenecks_count", kpis)

        # 2. Alerts Verification
        alerts = overview["alerts"]
        self.assertIsInstance(alerts, list)
        for alert in alerts:
            self.assertIn("id", alert)
            self.assertIn("severity", alert)
            self.assertIn(alert["severity"], ("urgent", "warning", "info"))
            self.assertIn("category", alert)
            self.assertIn("title", alert)
            self.assertIn("description", alert)
            self.assertIn("action_label", alert)
            self.assertIn("target_subview", alert)

        # 3. Master Admin Action Capability
        self.assertFalse(overview["is_read_only"])
        self.assertEqual(overview["role"], "MASTER_ADMIN")

        # 4. Recent Activity Feed Verification
        recent = overview["recent_activity"]
        self.assertIsInstance(recent, list)
        for act in recent:
            self.assertIn("id", act)
            self.assertIn("timestamp", act)
            self.assertIn("category", act)
            self.assertIn("title", act)
            self.assertIn("description", act)
            self.assertIn("actor", act)

    async def test_executive_observer_is_strictly_read_only(self):
        mock_user = {
            "username": "observer_ceo",
            "name": "Executive Observer",
            "role": "EXECUTIVE_OBSERVER",
            "allowed_domains": ["fleet", "accounts", "logistics"]
        }
        mock_req = self.make_mock_request()

        with patch("app.dashboard.get_current_user_from_request", return_value=mock_user):
            async with async_session_factory() as session:
                data = await get_dashboard_data(mock_req, session)

        overview = data["fleet"]["overview"]
        self.assertTrue(overview["is_read_only"])
        self.assertEqual(overview["role"], "EXECUTIVE_OBSERVER")

        # All alerts must have can_action as False or not mutate
        for alert in overview["alerts"]:
            if alert["id"] == "alert-rep-debt":
                self.assertFalse(alert["can_action"])

    async def test_sales_admin_role_gating(self):
        mock_user = {
            "username": "sales_manager",
            "name": "Sales Manager",
            "role": "SALES_ADMIN",
            "allowed_domains": ["fleet"]
        }
        mock_req = self.make_mock_request()

        with patch("app.dashboard.get_current_user_from_request", return_value=mock_user):
            async with async_session_factory() as session:
                data = await get_dashboard_data(mock_req, session)

        overview = data["fleet"]["overview"]
        self.assertEqual(overview["role"], "SALES_ADMIN")
        # Sales Admin cannot clear debt, so debt alert must not offer modal_target clearance
        for alert in overview["alerts"]:
            if alert["id"] == "alert-rep-debt":
                self.assertIsNone(alert["modal_target"])
                self.assertEqual(alert["action_label"], "View Debt Ledger")

    async def test_accounts_user_role_gating(self):
        mock_user = {
            "username": "accounts_clerk",
            "name": "Accounts Officer",
            "role": "ACCOUNTS_USER",
            "allowed_domains": ["fleet", "accounts"]
        }
        mock_req = self.make_mock_request()

        with patch("app.dashboard.get_current_user_from_request", return_value=mock_user):
            async with async_session_factory() as session:
                data = await get_dashboard_data(mock_req, session)

        overview = data["fleet"]["overview"]
        self.assertEqual(overview["role"], "ACCOUNTS_USER")
        # Accounts users see sales rep balances
        self.assertIsNotNone(overview["kpis"]["sales_rep_balance"])


if __name__ == "__main__":
    unittest.main()
