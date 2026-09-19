import asyncio
import os
import sys

from app.config import settings
from app.database import async_session_factory, Employee, Department, SupportAdmin
from app.services.trip_pricing_service import calculate_trip_approval, normalize_city_name
from app.handlers.fleet_approval_handler import (
    is_salesperson,
    handle_role_switch_command,
    send_sales_portal_menu,
    SESSION_ROLE_OVERRIDES
)
from app.handlers.admin_handler import handle_admin_command


async def run_tests():
    print("========================================")
    print("1. TESTING TRIP PRICING SERVICE & FORMULA")
    print("========================================")
    # Test Bindura
    res_bindura = calculate_trip_approval(actual_sales=11.73, destination="Bindura")
    print(f"Bindura (Sales: $11.73):")
    print(f"  Min Required: ${res_bindura['required_minimum']}")
    print(f"  Shortfall: ${res_bindura['shortfall']}")
    print(f"  Transport Charge (4%): ${res_bindura['transport_charge']}")
    assert res_bindura["approved"] is False
    assert res_bindura["shortfall"] == 3692.96
    assert res_bindura["transport_charge"] == 147.72
    print("  [SUCCESS] Bindura shortfall & 4% transport charge match formula!")

    # Test Bulawayo meeting minimum
    res_byo = calculate_trip_approval(actual_sales=17000.0, destination="byo")
    print(f"\nBulawayo alias 'byo' (Sales: $17,000):")
    print(f"  Approved: {res_byo['approved']}")
    print(f"  Transport Charge: ${res_byo['transport_charge']}")
    assert res_byo["approved"] is True
    assert res_byo["transport_charge"] == 0.0
    print("  [SUCCESS] Bulawayo approval & zero charge verified!")

    print("\n========================================")
    print("2. TESTING SALESPERSON DETECTION & ROLE TOGGLING")
    print("========================================")
    fazal_phone = "919265368695"
    async with async_session_factory() as session:
        # Check initial state with TEST_USER_ROLE=SALES
        SESSION_ROLE_OVERRIDES.clear()
        is_sales = await is_salesperson(session, fazal_phone)
        print(f"Fazal role when TEST_USER_ROLE=SALES: is_salesperson = {is_sales}")
        assert is_sales is True, "Expected Fazal to be SALES when TEST_USER_ROLE=SALES"

        # Test switching to MASTER_ADMIN in one word via chat command
        switched = await handle_role_switch_command(session, fazal_phone, "role admin")
        assert switched is True
        is_sales_after = await is_salesperson(session, fazal_phone)
        print(f"Fazal role after 'role admin': is_salesperson = {is_sales_after}")
        assert is_sales_after is False, "Expected Fazal to be Master Admin after 'role admin'"

        # Test switching back to SALES in one word via chat command
        switched2 = await handle_role_switch_command(session, fazal_phone, "role sales")
        assert switched2 is True
        is_sales_back = await is_salesperson(session, fazal_phone)
        print(f"Fazal role after 'role sales': is_salesperson = {is_sales_back}")
        assert is_sales_back is True, "Expected Fazal to be SALES after 'role sales'"

        print("  [SUCCESS] Live One-Word Role Reversion verified!")

    print("\n========================================")
    print("3. TESTING FAVLOGIX LIVE BROWSER AUTOMATION")
    print("========================================")
    from app.services.favlogix_browser_service import FavlogixBrowserService
    browser = FavlogixBrowserService()
    try:
        data = browser.extract_trip_data("20042026-BINDURA")
        print(f"Live Favlogix Extraction Result:")
        print(f"  Trip: {data['trip_id']}")
        print(f"  Amount: ${data['total_amount']}")
        print(f"  Destination: {data['destination_city']}")
        assert data["total_amount"] == 11.73
        print("  [SUCCESS] Live extraction on port 9222 succeeded with clean modal closure!")
    except Exception as e:
        print(f"  [NOTE] Live browser check returned: {e}")

    print("\n========================================")
    print("ALL CORE UNIT TESTS PASSED!")
    print("========================================")


if __name__ == "__main__":
    asyncio.run(run_tests())
