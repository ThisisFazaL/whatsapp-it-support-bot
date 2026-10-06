import unittest
from unittest.mock import patch, AsyncMock

from app.services.favlogix_api_service import (
    FavlogixAPIService,
    CompanyTenantSession,
    FavlogixCalculationPendingError
)
from app.services.trip_verification_service import TripVerificationService


class TestFavlogixMultiCompany(unittest.IsolatedAsyncioTestCase):
    """
    Test suite for Multi-Company Favlogix API tenant routing:
    - LG Plast
    - Tagoneswa Hardware
    - Kreckle Foods
    - Fallback default tenant
    """

    def setUp(self):
        self.service = FavlogixAPIService()

    def test_tenant_initialization(self):
        """Verifies all 3 company tenants and default tenant are registered."""
        self.assertIn("LG", self.service.tenants)
        self.assertIn("TG", self.service.tenants)
        self.assertIn("KRECKLE", self.service.tenants)
        self.assertIn("DEFAULT", self.service.tenants)

        self.assertEqual(self.service.tenants["LG"].display_name, "LG Plast")
        self.assertEqual(self.service.tenants["TG"].display_name, "Tagoneswa Hardware")
        self.assertEqual(self.service.tenants["KRECKLE"].display_name, "Kreckle Foods")

    @patch.dict("os.environ", {
        "LGPLAST_EMAIL": "lg_user@render.com",
        "LGPLAST_PASSWORD": "render_lg_pass",
        "TAGONESWA_EMAIL": "tg_user@render.com",
        "TAGONESWA_PASSWORD": "render_tg_pass",
        "KRECKLE_EMAIL": "kr_user@render.com",
        "KRECKLE_PASSWORD": "render_kr_pass",
    })
    def test_render_environment_aliases_initialization(self):
        """Verifies direct Render variable names (LGPLAST_EMAIL, etc.) correctly initialize the tenants."""
        service = FavlogixAPIService()
        self.assertEqual(service.tenants["LG"].email, "lg_user@render.com")
        self.assertEqual(service.tenants["LG"].password, "render_lg_pass")
        self.assertTrue(service.tenants["LG"].is_configured)

        self.assertEqual(service.tenants["TG"].email, "tg_user@render.com")
        self.assertEqual(service.tenants["TG"].password, "render_tg_pass")
        self.assertTrue(service.tenants["TG"].is_configured)

        self.assertEqual(service.tenants["KRECKLE"].email, "kr_user@render.com")
        self.assertEqual(service.tenants["KRECKLE"].password, "render_kr_pass")
        self.assertTrue(service.tenants["KRECKLE"].is_configured)

    def test_tenant_routing_by_company_name(self):
        """Verifies get_tenant routes correctly when company credentials are configured."""
        # Configure test credentials
        self.service.tenants["LG"].email = "lg_rep@favlogix.com"
        self.service.tenants["LG"].password = "Pass123"

        self.service.tenants["TG"].email = "tg_rep@favlogix.com"
        self.service.tenants["TG"].password = "Pass456"

        self.service.tenants["KRECKLE"].email = "kreckle_rep@favlogix.com"
        self.service.tenants["KRECKLE"].password = "Pass789"

        # 1. LG Plast
        tenant_lg = self.service.get_tenant(company_name="B. LG Plast")
        self.assertEqual(tenant_lg.company_key, "LG")

        # 2. Tagoneswa Hardware
        tenant_tg = self.service.get_tenant(company_name="A. TG Hardware")
        self.assertEqual(tenant_tg.company_key, "TG")

        # 3. Kreckle Foods
        tenant_kr = self.service.get_tenant(company_name="C. Kreckle")
        self.assertEqual(tenant_kr.company_key, "KRECKLE")

    def test_tenant_routing_by_trip_prefix(self):
        """Verifies get_tenant routes based on trip ID prefix when company_name is not passed."""
        self.service.tenants["LG"].email = "lg_rep@favlogix.com"
        self.service.tenants["LG"].password = "Pass123"

        self.service.tenants["TG"].email = "tg_rep@favlogix.com"
        self.service.tenants["TG"].password = "Pass456"

        self.service.tenants["KRECKLE"].email = "kreckle_rep@favlogix.com"
        self.service.tenants["KRECKLE"].password = "Pass789"

        self.assertEqual(self.service.get_tenant(trip_id="LG-2026-001").company_key, "LG")
        self.assertEqual(self.service.get_tenant(trip_id="TG-20042026-MUTARE").company_key, "TG")
        self.assertEqual(self.service.get_tenant(trip_id="KR-5544").company_key, "KRECKLE")

    def test_fallback_to_default_when_unconfigured(self):
        """When a tenant is matched but not yet configured with credentials, falls back to DEFAULT."""
        self.service.tenants["LG"].email = ""
        self.service.tenants["LG"].password = ""
        self.service.tenants["LG"].auth_token = ""
        self.service.tenants["LG"].cookies.clear()
        self.service.tenants["LG"].reg_code = ""

        tenant = self.service.get_tenant(company_name="B. LG Plast")
        self.assertEqual(tenant.company_key, "DEFAULT")

    def test_backwards_compatibility_properties(self):
        """Ensures legacy properties remain accessible."""
        self.assertTrue(hasattr(self.service, "api_url"))
        self.assertTrue(hasattr(self.service, "org_name_or_id"))
        self.assertTrue(hasattr(self.service, "email"))
        self.assertTrue(hasattr(self.service, "password"))
        self.assertTrue(hasattr(self.service, "auth_token"))
        self.assertTrue(hasattr(self.service, "is_fio"))
        self.assertTrue(hasattr(self.service, "base_url"))

    @patch.object(FavlogixAPIService, "_extract_from_tenant")
    async def test_multi_company_fallback_search(self, mock_extract):
        """
        If trip is not found on primary tenant, verifies fallback searches
        other configured tenants before failing.
        """
        # Configure TG and LG
        self.service.tenants["LG"].email = "lg@test.com"
        self.service.tenants["LG"].password = "pwd"
        self.service.tenants["TG"].email = "tg@test.com"
        self.service.tenants["TG"].password = "pwd"

        # Mock: LG fails (pending/not found), but TG succeeds
        async def side_effect(tenant, trip_id):
            if tenant.company_key == "LG":
                raise FavlogixCalculationPendingError("Not found on LG")
            elif tenant.company_key == "TG":
                return {
                    "trip_id": trip_id,
                    "company_name": "Tagoneswa Hardware",
                    "total_amount": 2500.0,
                    "destination_city": "Bulawayo",
                    "status": "CALCULATED"
                }
            raise FavlogixCalculationPendingError("Not found")

        mock_extract.side_effect = side_effect

        # User submitted as LG, but trip belonged to TG
        res = await self.service.extract_trip_data("TG-101", company_name="LG Plast")
        self.assertEqual(res["company_name"], "Tagoneswa Hardware")
        self.assertEqual(res["total_amount"], 2500.0)

    @patch("app.services.trip_verification_service.favlogix_api_service.extract_trip_data")
    async def test_trip_verification_service_company_forwarding(self, mock_api_extract):
        """Verifies verify_trip forwards company_name to extract_trip_data."""
        mock_api_extract.return_value = {
            "trip_id": "20042026-BYO",
            "company_name": "Tagoneswa Hardware",
            "total_amount": 3500.0,
            "destination_city": "Bulawayo",
            "status": "CALCULATED",
            "customers": [],
            "order_count": 1
        }

        tv_service = TripVerificationService()
        res = await tv_service.verify_trip("20042026-BYO", company_name="A. TG Hardware")

        mock_api_extract.assert_called_once_with("20042026-BYO", company_name="A. TG Hardware")
        self.assertTrue(res["success"])
        self.assertEqual(res["company_name"], "Tagoneswa Hardware")
        self.assertEqual(res["total_amount"], 3500.0)

    @patch("httpx.AsyncClient.post")
    async def test_enroll_device_and_challenge_login(self, mock_post):
        """Tests ECDSA key generation, device enrollment, and challenge signature verification flow."""
        from unittest.mock import MagicMock
        tenant = self.service.tenants["LG"]
        tenant.password = "secret123"

        # Mock enrollment response
        mock_enroll_resp = MagicMock()
        mock_enroll_resp.status_code = 200
        mock_enroll_resp.json.return_value = {
            "data": {"device": {"key": "test_device_key_12345"}}
        }

        mock_post.return_value = mock_enroll_resp
        enrolled = await self.service.enroll_device(tenant, reg_code="ABC12345")
        self.assertTrue(enrolled)
        self.assertEqual(tenant.device_key, "test_device_key_12345")
        self.assertEqual(tenant.cookies.get("device_id"), "test_device_key_12345")
        self.assertIsNotNone(tenant.private_key)

        # Mock login response returning challenge
        mock_login_resp = MagicMock()
        mock_login_resp.status_code = 200
        mock_login_resp.cookies = {"session": "pre_session_cookie"}
        mock_login_resp.text = '{"data": {"challenge": "random_test_challenge_string", "slug": "lgplast", "deviceKey": "test_device_key_12345"}}'
        mock_login_resp.json.return_value = {
            "data": {
                "challenge": "random_test_challenge_string",
                "slug": "lgplast",
                "deviceKey": "test_device_key_12345",
                "employeeConfigKey": "emp_123"
            }
        }

        # Mock verify response returning authenticated token
        mock_verify_resp = MagicMock()
        mock_verify_resp.status_code = 200
        mock_verify_resp.cookies = {"session": "auth_cookie_final"}
        mock_verify_resp.text = '{"data": {"token": "header.payload.signature"}}'
        mock_verify_resp.json.return_value = {
            "data": {"token": "header.payload.signature"}
        }

        mock_post.side_effect = [mock_login_resp, mock_verify_resp]
        token = await self.service._login(tenant)
        self.assertEqual(token, "header.payload.signature")
        self.assertEqual(tenant.auth_token, "header.payload.signature")


if __name__ == "__main__":
    unittest.main()

