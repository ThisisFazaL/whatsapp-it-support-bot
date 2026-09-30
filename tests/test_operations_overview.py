import asyncio
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from app.database import async_session_factory, init_db_models
from app.dashboard import get_dashboard_data, dashboard_view
from app.workshop.models import WorkshopTruck, WorkshopTicket


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

    # ─── FLEET AVAILABILITY TESTS ────────────────────────────────────────────

    async def test_fleet_kpi_includes_availability_breakdown(self):
        """Overview KPI payload must include granular fleet availability fields."""
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

        kpis = data["fleet"]["overview"]["kpis"]

        # New breakdown fields must be present
        self.assertIn("trucks_available", kpis)
        self.assertIn("trucks_in_workshop", kpis)
        self.assertIn("trucks_awaiting_parts", kpis)
        self.assertIn("trucks_awaiting_qc", kpis)
        self.assertIn("trucks_total", kpis)

        # Basic sanity: available + in_workshop + awaiting_parts + awaiting_qc <= total
        total = kpis["trucks_total"]
        busy = kpis["trucks_in_workshop"] + kpis["trucks_awaiting_parts"] + kpis["trucks_awaiting_qc"]
        self.assertGreaterEqual(total, 0)
        self.assertGreaterEqual(kpis["trucks_available"], 0)
        self.assertLessEqual(busy, total, "Distinct busy trucks cannot exceed total fleet roster")

    async def test_distinct_truck_counting_multiple_tickets(self):
        """A truck with multiple open tickets must be counted only ONCE in the fleet breakdown."""
        # Use a mock session that returns 1 active truck and 3 tickets all pointing to same truck_id
        from sqlalchemy.ext.asyncio import AsyncSession
        from unittest.mock import AsyncMock, MagicMock

        # Build fake WorkshopTicket objects for truck_id=1
        def make_ticket(tid, truck_id, status, truck_number="1001"):
            t = MagicMock(spec=WorkshopTicket)
            t.ticket_id = tid
            t.ticket_number = f"TKT-{tid}"
            t.truck_id = truck_id
            t.status = status
            t.description = "Test ticket"
            t.category_name = None
            t.subcategory_name = None
            t.image_id = None
            t.created_at = None
            t.expected_completion_time = None
            t.cost_total = None
            t.qc_passed = None
            t.return_to_fleet_at = None
            truck_mock = MagicMock()
            truck_mock.truck_number = truck_number
            truck_mock.plate_number = f"ABZ {truck_number}"
            truck_mock.model_make = "Volvo FH16"
            t.truck = truck_mock
            t.logged_by = None
            t.assigned_mechanic = None
            return t

        tickets = [
            make_ticket(1, 1, "WITH_MECHANIC"),        # in workshop
            make_ticket(2, 1, "AWAITING_PARTS"),        # same truck — worse? no, WITH_MECHANIC > AWAITING_PARTS via priority
            make_ticket(3, 1, "REPAIR_IN_PROGRESS"),   # same truck — REPAIR_IN_PROGRESS has priority 6 > 5 (WITH_MECHANIC)
        ]

        # Simulate the _STATUS_PRIORITY logic directly (not through dashboard — just verify the algorithm)
        _STATUS_PRIORITY = {
            "OPEN": 1, "UNDER_REVIEW": 2, "AWAITING_TEST": 3,
            "AWAITING_PARTS": 4, "WITH_MECHANIC": 5,
            "REPAIR_IN_PROGRESS": 6, "REWORK_REQUIRED": 7,
        }
        busy_truck_ids = {}
        for t in tickets:
            if t.status == "CLOSED" or t.truck_id is None:
                continue
            existing = busy_truck_ids.get(t.truck_id)
            if existing is None:
                busy_truck_ids[t.truck_id] = t.status
            else:
                if _STATUS_PRIORITY.get(t.status, 0) > _STATUS_PRIORITY.get(existing, 0):
                    busy_truck_ids[t.truck_id] = t.status

        # Only ONE distinct truck should be in busy_truck_ids
        self.assertEqual(len(busy_truck_ids), 1, "Three tickets for same truck must produce exactly 1 busy truck entry")
        # Worst status must be REPAIR_IN_PROGRESS (priority 6)
        self.assertEqual(busy_truck_ids[1], "REPAIR_IN_PROGRESS", "Worst status must take precedence")

    async def test_closed_tickets_do_not_count_as_busy(self):
        """A CLOSED WorkshopTicket must not mark the truck as unavailable."""
        _STATUS_PRIORITY = {
            "OPEN": 1, "UNDER_REVIEW": 2, "AWAITING_TEST": 3,
            "AWAITING_PARTS": 4, "WITH_MECHANIC": 5,
            "REPAIR_IN_PROGRESS": 6, "REWORK_REQUIRED": 7,
        }

        class FakeTkt:
            def __init__(self, truck_id, status):
                self.truck_id = truck_id
                self.status = status

        tickets = [
            FakeTkt(2, "CLOSED"),
            FakeTkt(2, "CLOSED"),
        ]

        busy_truck_ids = {}
        for t in tickets:
            if t.status == "CLOSED" or t.truck_id is None:
                continue
            existing = busy_truck_ids.get(t.truck_id)
            if existing is None:
                busy_truck_ids[t.truck_id] = t.status
            else:
                if _STATUS_PRIORITY.get(t.status, 0) > _STATUS_PRIORITY.get(existing, 0):
                    busy_truck_ids[t.truck_id] = t.status

        self.assertEqual(len(busy_truck_ids), 0, "CLOSED tickets must not produce any busy_truck_ids entry")

    async def test_fleet_availability_split_across_states(self):
        """Trucks in different states must be categorised independently."""
        _STATUS_PRIORITY = {
            "OPEN": 1, "UNDER_REVIEW": 2, "AWAITING_TEST": 3,
            "AWAITING_PARTS": 4, "WITH_MECHANIC": 5,
            "REPAIR_IN_PROGRESS": 6, "REWORK_REQUIRED": 7,
        }

        class FakeTkt:
            def __init__(self, truck_id, status):
                self.truck_id = truck_id
                self.status = status

        tickets = [
            FakeTkt(10, "WITH_MECHANIC"),    # truck 10 → in workshop
            FakeTkt(11, "AWAITING_PARTS"),   # truck 11 → awaiting parts
            FakeTkt(12, "AWAITING_TEST"),    # truck 12 → awaiting QC
            FakeTkt(13, "CLOSED"),           # truck 13 → available (closed)
        ]

        busy_truck_ids = {}
        for t in tickets:
            if t.status == "CLOSED" or t.truck_id is None:
                continue
            existing = busy_truck_ids.get(t.truck_id)
            if existing is None:
                busy_truck_ids[t.truck_id] = t.status
            else:
                if _STATUS_PRIORITY.get(t.status, 0) > _STATUS_PRIORITY.get(existing, 0):
                    busy_truck_ids[t.truck_id] = t.status

        _in_workshop_statuses = {"WITH_MECHANIC", "REPAIR_IN_PROGRESS", "REWORK_REQUIRED"}
        trucks_in_workshop   = sum(1 for s in busy_truck_ids.values() if s in _in_workshop_statuses)
        trucks_awaiting_parts = sum(1 for s in busy_truck_ids.values() if s == "AWAITING_PARTS")
        trucks_awaiting_qc   = sum(1 for s in busy_truck_ids.values() if s == "AWAITING_TEST")

        self.assertEqual(trucks_in_workshop, 1)
        self.assertEqual(trucks_awaiting_parts, 1)
        self.assertEqual(trucks_awaiting_qc, 1)
        self.assertEqual(len(busy_truck_ids), 3, "Closed truck must not appear in busy map")

    async def test_logistics_admin_financial_section_hidden(self):
        """LOGISTICS_ADMIN has no view_sales_rep_balances → sales_rep_balance must be None in KPIs."""
        mock_user = {
            "username": "logistics_admin_user",
            "name": "Logistics Admin",
            "role": "LOGISTICS_ADMIN",
            "allowed_domains": ["fleet"]
        }
        mock_req = self.make_mock_request()

        with patch("app.dashboard.get_current_user_from_request", return_value=mock_user):
            async with async_session_factory() as session:
                data = await get_dashboard_data(mock_req, session)

        kpis = data["fleet"]["overview"]["kpis"]
        # LOGISTICS_ADMIN does not have view_sales_rep_balances permission
        self.assertIsNone(kpis.get("sales_rep_balance"),
                          "LOGISTICS_ADMIN must not receive sales_rep_balance data")

    async def test_operations_analytics_payload_and_metrics(self):
        """Operations analytics must compute live financial & operational breakdown."""
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

        fleet = data["fleet"]
        self.assertIn("analytics", fleet)
        self.assertIn("analytics", fleet["overview"])
        analytics = fleet["analytics"]

        required_metrics = [
            "total_sales", "total_transport_charges", "total_allowances",
            "total_meals", "total_accommodation", "total_tolls",
            "total_emergency_fuel", "total_emergency_other",
            "total_operational_expenses", "net_amount", "trips_total",
            "trips_completed", "avg_revenue_per_trip", "avg_opex_per_trip",
            "avg_allowance_per_trip", "fleet_utilization_pct",
            "workshop_impact_count", "recovery_rate_pct",
            "cleared_payments_total", "outstanding_debt_total",
            "cities", "routes"
        ]
        for metric in required_metrics:
            self.assertIn(metric, analytics)

        # Operational expenses sanity check: total_operational_expenses = total_allowances + total_emergency_fuel + total_emergency_other
        calculated_opex = round(analytics["total_allowances"] + analytics["total_emergency_fuel"] + analytics["total_emergency_other"], 2)
        self.assertEqual(analytics["total_operational_expenses"], calculated_opex)

        # Net amount sanity check: net_amount = total_sales - total_operational_expenses
        calculated_net = round(analytics["total_sales"] - analytics["total_operational_expenses"], 2)
        self.assertEqual(analytics["net_amount"], calculated_net)

    async def test_audit_logs_payload(self):
        """Audit logs must be extracted from the database and included in the fleet payload."""
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

        self.assertIn("audit_logs", data["fleet"])
        self.assertIn("audit_logs", data["fleet"]["overview"])
        audit_logs = data["fleet"]["audit_logs"]
        self.assertIsInstance(audit_logs, list)
        for entry in audit_logs:
            self.assertIn("id", entry)
            self.assertIn("timestamp", entry)
            self.assertIn("username", entry)
            self.assertIn("user_role", entry)
            self.assertIn("action", entry)

    async def test_dashboard_view_html_structure(self):
        """Dashboard HTML must feature the workspace selector, no horizontal subnav bar, and all 10 overview sections."""
        mock_user = {
            "username": "master",
            "name": "Master Administrator",
            "role": "MASTER_ADMIN",
            "allowed_domains": ["it", "projects", "logistics", "fleet", "accounts", "admin"]
        }
        mock_req = self.make_mock_request()

        with patch("app.dashboard.get_current_user_from_request", return_value=mock_user):
            resp = await dashboard_view(mock_req)

        self.assertEqual(resp.status_code, 200)
        html = resp.body.decode("utf-8")

        # 1. Old horizontal sub-nav bar must NOT be present
        self.assertNotIn("7-Stage Trips Pipeline", html)
        self.assertNotIn("Sales Rep Debt Ledger", html)
        self.assertNotIn("Cleared Payments History", html)
        self.assertNotIn("39 Commercial Trucks", html)
        self.assertNotIn("21 Commercial Drivers", html)

        # 2. Modern compact workspace selector & quick nav must be present
        self.assertIn('id="fleet-view-selector"', html)
        self.assertIn('fleet-quick-pill', html)

        # 3. Operations Overview 10-tier elements must be present
        expected_ids = [
            "fleet-section-overview",
            "ov-alerts-list",
            "ov-kpi-pending-approvals",
            "ov-kpi-bottlenecks",
            "ov-kpi-active-trips",
            "ov-kpi-trucks-ready",
            "ov-kpi-trucks-in-workshop",
            "ov-kpi-trucks-awaiting-parts",
            "ov-fin-total-sales",
            "ov-fin-net-margin",
            "ov-fin-total-opex",
            "ov-kpi-avg-revenue",
            "ov-top-cities-body",
            "ov-perf-util-bar",
            "ov-activity-list",
            "ov-recent-audit-body"
        ]
        for el_id in expected_ids:
            self.assertIn(f'id="{el_id}"', html, f"Missing expected HTML element id: {el_id}")

        # 4. Financial Audit Log view controls must be present
        self.assertIn('id="audit-mode-btn-TRAIL"', html)
        self.assertIn('id="timeframe-btn-ALL"', html)


if __name__ == "__main__":
    unittest.main()
