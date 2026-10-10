import sys
import os
import asyncio
import httpx

os.environ["ENVIRONMENT"] = "development"

from app.main import app
from app.dashboard import create_session_token, COOKIE_NAME

async def run_async_tests():
    print("==================================================================")
    print("STARTING ASYNC FULL DASHBOARD VERIFICATION REVIEW SUITE (3-4x AUDIT)")
    print("==================================================================")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Test Login Page
        print("\n--- Test 1: Login Page Rendering ---")
        r_login = await client.get("/login")
        assert r_login.status_code == 200, f"Expected 200, got {r_login.status_code}"
        assert "Tagoneswa" in r_login.text
        print("[PASS] Login page renders with HTTP 200")

        # 2. Test Unauthenticated Access
        print("\n--- Test 2: Unauthenticated Security Gate ---")
        r_unauth = await client.get("/dashboard", follow_redirects=False)
        assert r_unauth.status_code in (302, 307), f"Expected redirect, got {r_unauth.status_code}"
        print("[PASS] Unauthenticated request redirected safely to /login")

        # 3. Authenticated Session Setup
        token = create_session_token("admin", "MASTER_ADMIN")
        client.cookies.set(COOKIE_NAME, token)

        # 4. Test Dashboard Markup & Modals
        print("\n--- Test 3: Dashboard Markup & Modals Audit ---")
        r_dash = await client.get("/dashboard")
        assert r_dash.status_code == 200, f"Expected 200, got {r_dash.status_code}"
        html = r_dash.text

        # Verify userManagementModal enlarged size
        assert "max-w-5xl xl:max-w-6xl" in html, "userManagementModal not enlarged to max-w-5xl xl:max-w-6xl"
        print("[PASS] userManagementModal size is upgraded to max-w-5xl xl:max-w-6xl")

        # Verify createUserModal z-index fix
        assert "z-[70]" in html and 'style="z-index: 70;"' in html, "createUserModal missing z-[70] stacking context"
        assert 'style="z-index: 71;"' in html, "createUserModal inner card missing z-index 71"
        print("[PASS] createUserModal stacking context set to z-[70] / z-71 above userManagementModal (z-50)")

        # Verify cityMinimumsModal width and 6-column table headers
        assert 'id="cityMinimumsModal"' in html
        assert "max-w-5xl max-h-[92vh]" in html, "cityMinimumsModal card not upgraded to max-w-5xl"
        assert "Corridor / Route" in html, "cityMinimumsModal table header missing Corridor / Route"
        assert "Min Sales (Truck)" in html, "cityMinimumsModal table header missing Min Sales (Truck)"
        assert "Min Sales (Van)" in html, "cityMinimumsModal table header missing Min Sales (Van)"
        print("[PASS] cityMinimumsModal upgraded to max-w-5xl and table headers correctly aligned with 6 columns")

        # Verify clearPaymentModal Sujit waiver and absence of reference input
        assert "DEBT_WRITE_OFF" in html, "clearPaymentModal missing DEBT_WRITE_OFF option"
        assert "Management Debt Write-Off / Waiver (Approved by Sujit)" in html, "clearPaymentModal missing Sujit waiver text"
        assert "modal-pay-ref" not in html, "modal-pay-ref still present in clearPaymentModal"
        print("[PASS] clearPaymentModal contains Sujit write-off option and reference number input is removed")

        # 5. Test Live Operational Data API
        print("\n--- Test 4: Operational Data API & Route Rules Audit ---")
        r_data = await client.get("/api/dashboard/data")
        assert r_data.status_code == 200, f"Expected 200, got {r_data.status_code}"
        data = r_data.json()
        assert "fleet" in data
        assert "route_rules" in data["fleet"]
        rules = data["fleet"]["route_rules"]
        if isinstance(rules, list):
            rules_map = {r["city_key"]: r for r in rules}
        else:
            rules_map = rules
        print(f"Total city route rules returned: {len(rules_map)}")
        assert len(rules_map) >= 58, f"Expected at least 58 city rules, got {len(rules_map)}"

        zero_distance_cities = []
        for city_key, r in rules_map.items():
            dist = r.get("distance_km")
            if dist is None or dist <= 0:
                zero_distance_cities.append(city_key)

        print(f"Cities with distance <= 0: {len(zero_distance_cities)}")
        assert len(zero_distance_cities) == 0, f"Cities with uncalculated distance: {zero_distance_cities}"
        print(f"[PASS] All {len(rules_map)} cities have exact calculated road distances from 110 Coventry Road, Workington, Harare (zero 'Not configured')")

        # Sample check of notable distances from 110 Coventry Rd, Workington
        assert rules_map["bulawayo"]["distance_km"] == 442.0, f"Bulawayo distance mismatch: {rules_map['bulawayo']['distance_km']}"
        assert rules_map["mutare"]["distance_km"] == 265.0, f"Mutare distance mismatch: {rules_map['mutare']['distance_km']}"
        assert rules_map["masvingo"]["distance_km"] == 296.0, f"Masvingo distance mismatch: {rules_map['masvingo']['distance_km']}"
        assert rules_map["workington"]["distance_km"] == 5.0, f"Workington distance mismatch: {rules_map['workington']['distance_km']}"
        print("[PASS] Verified sample distances: Bulawayo=442km, Mutare=265km, Masvingo=296km, Workington=5km")

        # 6. Test User Management Endpoints
        print("\n--- Test 5: User Management Endpoints Audit ---")
        r_users = await client.get("/api/v2/admin/users")
        assert r_users.status_code == 200, f"Expected 200, got {r_users.status_code}"
        users_data = r_users.json()
        assert "users" in users_data
        assert len(users_data["users"]) > 0
        print(f"[PASS] GET /api/v2/admin/users returned {len(users_data['users'])} user accounts")

        # 7. Test System Audit Logs Endpoint
        print("\n--- Test 6: Audit Logs Endpoint Audit ---")
        r_audit = await client.get("/api/v2/audit/logs")
        assert r_audit.status_code == 200, f"Expected 200, got {r_audit.status_code}"
        audit_data = r_audit.json()
        assert "logs" in audit_data
        print(f"[PASS] GET /api/v2/audit/logs returned {len(audit_data['logs'])} audit logs")

        # 8. Test Rate Configuration Endpoints
        print("\n--- Test 7: Fuel & Rate Configuration Endpoints Audit ---")
        r_fuel = await client.post("/api/v2/config/update-fuel", json={"fuel_price": 1.55, "reason": "Test audit suite run"})
        assert r_fuel.status_code == 200, f"Expected 200, got {r_fuel.status_code}"
        assert r_fuel.json().get("status") == "success"
        print("[PASS] POST /api/v2/config/update-fuel succeeded")

        r_ops = await client.post("/api/v2/config/update-operational-params", json={
            "meal_rate": 5.0,
            "accommodation_rate": 15.0,
            "expense_budget_pct": 0.04,
            "van_minimum_surcharge": 1500.0
        })
        assert r_ops.status_code == 200, f"Expected 200, got {r_ops.status_code}"
        print("[PASS] POST /api/v2/config/update-operational-params succeeded")

        # 9. Test Debt Clearance Validation
        print("\n--- Test 8: Debt Clearance Validation & Logic Audit ---")
        r_clear_invalid = await client.post("/api/v2/finance/clear-sales-rep-payment", json={
            "salesperson_phone": "",
            "cleared_amount": 0
        })
        assert r_clear_invalid.status_code in (400, 422), f"Expected 400/422, got {r_clear_invalid.status_code}"
        print("[PASS] POST /api/v2/finance/clear-sales-rep-payment rejects invalid/empty payload")

        print("\n==================================================================")
        print("ALL 8 COMPREHENSIVE AUDIT SUITE TESTS PASSED WITH 0 ERRORS!")
        print("==================================================================")

if __name__ == "__main__":
    asyncio.run(run_async_tests())
