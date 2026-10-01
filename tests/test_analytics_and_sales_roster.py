import unittest
from unittest.mock import patch, MagicMock
from app.database import async_session_factory, init_db_models
from app.dashboard import get_dashboard_data, dashboard_view, OFFICIAL_SALES_REPS_DIRECTORY


class TestAnalyticsAndSalesRoster(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await init_db_models()

    def make_mock_request(self):
        req = MagicMock()
        req.cookies = {}
        req.headers = {}
        return req

    async def test_all_commercial_sales_reps_present_in_dashboard(self):
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

        fleet = data.get("fleet", {})
        self.assertIsNotNone(fleet)
        salespersons = fleet.get("salespersons", [])
        self.assertGreater(len(salespersons), 0)

        sp_phones = {sp["phone"] for sp in salespersons}
        for phone, info in OFFICIAL_SALES_REPS_DIRECTORY.items():
            self.assertIn(phone, sp_phones, f"Official sales rep {info['name']} ({phone}) should be in salespersons list")

        # Verify company labels exist
        sp_companies = {sp.get("company") for sp in salespersons}
        self.assertTrue(any("LG Plast" in str(c) for c in sp_companies))
        self.assertTrue(any("Tagoneswa" in str(c) for c in sp_companies))
        self.assertTrue(any("Kreckle" in str(c) for c in sp_companies))

    async def test_analytics_payload_and_chart_elements(self):
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
                html_resp = await dashboard_view(mock_req)

        fleet = data.get("fleet", {})
        an = fleet.get("analytics", {})
        self.assertIn("trips_total", an)
        self.assertIn("total_operational_expenses", an)
        self.assertIn("cities", an)
        self.assertIn("routes", an)

        # HTML verification
        html_body = html_resp.body.decode("utf-8")
        self.assertIn("chart.js", html_body.lower(), "Chart.js CDN should be included in HTML head")
        self.assertIn('id="an-pipeline-chart"', html_body, "Pipeline chart canvas should be present")
        self.assertIn('id="an-cost-donut-chart"', html_body, "Cost donut chart canvas should be present")
        self.assertIn('id="an-corridors-bar-chart"', html_body, "Corridors bar chart canvas should be present")
        self.assertIn('id="an-financial-overview-chart"', html_body, "Financial overview chart canvas should be present")
        self.assertIn('id="sp-company-filters"', html_body, "Company filter bar should be present")
