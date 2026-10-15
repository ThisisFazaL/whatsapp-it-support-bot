import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch

from sqlalchemy import select, delete
from app.database import (
    async_session_factory,
    FleetTripRequest,
    FleetCustomerSchedule,
    FleetPendingLedger,
    get_fleet_trip_request_by_id,
    get_sales_rep_pending_balance
)
from app.state_manager import clear_user_state, get_user_state, normalize_phone_number
from app.handlers.sales_admin_handler import (
    notify_sales_admin_balancing_session,
    handle_sales_admin_interaction
)
from app.config import settings

def clean_phone(p):
    return normalize_phone_number(str(p or ""))

async def run_tests():
    print("=== STARTING SALES ADMIN BALANCING & FAVLOGIX DISCREPANCY RECONCILIATION TESTS ===")
    
    admin_phone = "263772223344"
    sales_rep_phone = "263773334455"
    driver_phone = "263774445566"
    test_trip_id = "TEST-BAL-001"
    
    # Setup test trip & clean test data
    async with async_session_factory() as s:
        await s.execute(delete(FleetTripRequest).where(FleetTripRequest.trip_id == test_trip_id))
        await s.execute(delete(FleetCustomerSchedule).where(FleetCustomerSchedule.trip_id == test_trip_id))
        await s.execute(delete(FleetPendingLedger).where(FleetPendingLedger.trip_id == test_trip_id))
        await s.commit()

        trip = FleetTripRequest(
            trip_id=test_trip_id,
            company_name="Tagoneswa Hardware",
            destination_city="Harare",
            route="Harare Local",
            salesperson_phone=sales_rep_phone,
            salesperson_name="Test Salesperson",
            sales_admin_phone=admin_phone,
            driver_phone=driver_phone,
            driver_name="Test Driver",
            truck_plate="ABC-1234",
            status="RETURNED"
        )
        s.add(trip)
        await s.commit()

    # ------------------------------------------------------------------------
    # TEST CASE 1: Sales Admin clicks [Balanced] -> Offered Close Trip directly
    # ------------------------------------------------------------------------
    print("\n--- TEST CASE 1: SALES ADMIN CLICKS BALANCED -> OFFERED CLOSE TRIP ---")
    with patch("app.meta_api.meta_api.send_button_message", new_callable=AsyncMock) as mock_btn, \
         patch("app.meta_api.meta_api.send_text_message", new_callable=AsyncMock) as mock_txt:
        async with async_session_factory() as s:
            await clear_user_state(s, admin_phone)

            handled = await handle_sales_admin_interaction(s, admin_phone, f"flt_adm_bal_{test_trip_id}", None)
            assert handled is True, "flt_adm_bal_ should be handled"

            trip_check = await get_fleet_trip_request_by_id(s, test_trip_id)
            assert trip_check.status == "BALANCED"
            print("[PASS] DB status updated to BALANCED.")

            assert mock_btn.call_count >= 1
            call_kwargs = mock_btn.call_args[1]
            buttons = call_kwargs.get("buttons", [])
            assert any(b.get("id") == f"flt_adm_close_{test_trip_id}" for b in buttons), "Should provide Close Trip button"
            print("[PASS] Sales admin received [Close Trip] button directly instead of sending to Zayn.")

    # ------------------------------------------------------------------------
    # TEST CASE 2: Sales Admin clicks [Close Trip] -> Trip officially CLOSED
    # ------------------------------------------------------------------------
    print("\n--- TEST CASE 2: SALES ADMIN CLICKS CLOSE TRIP ---")
    with patch("app.meta_api.meta_api.send_text_message", new_callable=AsyncMock) as mock_txt:
        async with async_session_factory() as s:
            handled = await handle_sales_admin_interaction(s, admin_phone, f"flt_adm_close_{test_trip_id}", None)
            assert handled is True

            trip_check = await get_fleet_trip_request_by_id(s, test_trip_id)
            assert trip_check.status == "CLOSED"
            print("[PASS] DB status verified: CLOSED by Sales Admin.")

    # ------------------------------------------------------------------------
    # TEST CASE 3: Sales Admin clicks [Not Balanced] -> Prompt for Collected Amount
    # ------------------------------------------------------------------------
    print("\n--- TEST CASE 3: SALES ADMIN CLICKS NOT BALANCED -> PROMPT FOR AMOUNT ---")
    with patch("app.meta_api.meta_api.send_text_message", new_callable=AsyncMock) as mock_txt:
        async with async_session_factory() as s:
            trip = await get_fleet_trip_request_by_id(s, test_trip_id)
            trip.status = "RETURNED"
            await s.commit()

            handled = await handle_sales_admin_interaction(s, admin_phone, f"flt_adm_unbal_{test_trip_id}", None)
            assert handled is True
            prompt = mock_txt.call_args[0][1]
            assert "enter the actual collected transportation amount" in prompt.lower()
            st = await get_user_state(s, admin_phone)
            assert st.current_step == "awaiting_sales_admin_collected_amount"
            print("[PASS] Sales admin prompted for collected amount.")

    # ------------------------------------------------------------------------
    # TEST CASE 4: Sales Admin Enters Amount that matches FavLogix report
    # ------------------------------------------------------------------------
    print("\n--- TEST CASE 4: AMOUNT MATCHES FAVLOGIX REPORT ---")
    mock_favlogix_report = {
        "found": True,
        "trip_id": test_trip_id,
        "collected": 950.57,
        "collected_cash": 950.57,
        "source": "trip_report"
    }
    with patch("app.services.favlogix_api_service.favlogix_api_service.get_trip_report_data", new_callable=AsyncMock, return_value=mock_favlogix_report), \
         patch("app.meta_api.meta_api.send_button_message", new_callable=AsyncMock) as mock_btn, \
         patch("app.meta_api.meta_api.send_text_message", new_callable=AsyncMock) as mock_txt:
        async with async_session_factory() as s:
            st = await get_user_state(s, admin_phone)
            handled = await handle_sales_admin_interaction(s, admin_phone, "950.57", st)
            assert handled is True

            call_kwargs = mock_btn.call_args[1]
            body = call_kwargs.get("body_text", "")
            assert "MATCH FAVLOGIX RECORD" in body
            assert "$950.57" in body
            buttons = call_kwargs.get("buttons", [])
            assert any(b.get("id") == f"flt_adm_close_{test_trip_id}" for b in buttons)
            print("[PASS] Matched amounts confirmed as balanced and offered [Close Trip].")

    # ------------------------------------------------------------------------
    # TEST CASE 5: Discrepancy -> Stores Difference & Gives 'Updated' Button
    # ------------------------------------------------------------------------
    print("\n--- TEST CASE 5: DISCREPANCY DETECTED -> STORES DIFF & PROMPTS WITH 'UPDATED' BUTTON ---")
    # Favlogix says collected: $950.57
    # Sales admin says counted: $800.00
    # Expected Diff = 950.57 - 800.00 = 150.57
    with patch("app.services.favlogix_api_service.favlogix_api_service.get_trip_report_data", new_callable=AsyncMock, return_value=mock_favlogix_report), \
         patch("app.meta_api.meta_api.send_button_message", new_callable=AsyncMock) as mock_btn, \
         patch("app.meta_api.meta_api.send_text_message", new_callable=AsyncMock) as mock_txt:
        async with async_session_factory() as s:
            from app.state_manager import set_user_state
            await set_user_state(s, admin_phone, "awaiting_sales_admin_collected_amount", {"trip_id": test_trip_id}, flow_name="fleet_sales_admin")
            st = await get_user_state(s, admin_phone)

            handled = await handle_sales_admin_interaction(s, admin_phone, "800.00", st)
            assert handled is True

            # Sales Admin card check
            call_kwargs = mock_btn.call_args[1]
            body = call_kwargs.get("body_text", "")
            assert "DISCREPANCY DETECTED" in body
            assert "950.57" in body
            assert "800.00" in body
            assert "150.57" in body
            buttons = call_kwargs.get("buttons", [])
            assert any(b.get("id") == f"flt_adm_fav_updated_{test_trip_id}" for b in buttons), "Should provide Updated button"
            
            # Check state
            st_check = await get_user_state(s, admin_phone)
            assert st_check.current_step == "awaiting_favlogix_update_confirm"
            assert st_check.current_data.get("initial_diff") == 150.57
            assert st_check.current_data.get("admin_collected") == 800.0
            print("[PASS] Sales admin received discrepancy breakdown ($150.57) and 'Updated' button.")

    # ------------------------------------------------------------------------
    # TEST CASE 6: Sales Admin Taps 'Updated' but FavLogix has NOT been updated yet
    # ------------------------------------------------------------------------
    print("\n--- TEST CASE 6: 'UPDATED' PRESSED BUT FAVLOGIX STILL HAS OLD VALUE ---")
    mock_favlogix_unmodified = {
        "found": True,
        "trip_id": test_trip_id,
        "collected": 950.57,  # Still 950.57
        "source": "trip_report"
    }
    with patch("app.services.favlogix_api_service.favlogix_api_service.get_trip_report_data", new_callable=AsyncMock, return_value=mock_favlogix_unmodified), \
         patch("app.meta_api.meta_api.send_button_message", new_callable=AsyncMock) as mock_btn:
        async with async_session_factory() as s:
            st = await get_user_state(s, admin_phone)
            handled = await handle_sales_admin_interaction(s, admin_phone, f"flt_adm_fav_updated_{test_trip_id}", st)
            assert handled is True

            call_kwargs = mock_btn.call_args[1]
            body = call_kwargs.get("body_text", "")
            assert "NOT MATCHING YET" in body
            assert "950.57" in body
            buttons = call_kwargs.get("buttons", [])
            assert any(b.get("id") == f"flt_adm_fav_updated_{test_trip_id}" for b in buttons)

            st_after = await get_user_state(s, admin_phone)
            assert st_after.current_step == "awaiting_favlogix_update_confirm"
            print("[PASS] Bot correctly detected FavLogix still not updated, re-prompted with 'Updated' button.")

    # ------------------------------------------------------------------------
    # TEST CASE 7: Sales Admin Updates FavLogix -> Matches -> Diff Added to Rep Ledger & Close Button
    # ------------------------------------------------------------------------
    print("\n--- TEST CASE 7: FAVLOGIX UPDATED -> MATCHES -> DIFF ADDED TO REP LEDGER & CLOSE BUTTON ---")
    mock_favlogix_updated = {
        "found": True,
        "trip_id": test_trip_id,
        "collected": 800.00,  # Now updated in FavLogix to 800.00!
        "source": "trip_report"
    }
    with patch("app.services.favlogix_api_service.favlogix_api_service.get_trip_report_data", new_callable=AsyncMock, return_value=mock_favlogix_updated), \
         patch("app.meta_api.meta_api.send_button_message", new_callable=AsyncMock) as mock_btn, \
         patch("app.meta_api.meta_api.send_text_message", new_callable=AsyncMock) as mock_txt:
        async with async_session_factory() as s:
            st = await get_user_state(s, admin_phone)
            handled = await handle_sales_admin_interaction(s, admin_phone, f"flt_adm_fav_updated_{test_trip_id}", st)
            assert handled is True

            # 1. Sales rep pending ledger check
            bal = await get_sales_rep_pending_balance(s, sales_rep_phone)
            assert bal == 150.57, f"Expected pending balance 150.57, got {bal}"
            print(f"[PASS] Diff of $150.57 added to Sales Representative's pending ledger (New Bal: ${bal:.2f}).")

            # 2. Sales rep notification check
            rep_notified = False
            for call in mock_txt.call_args_list:
                to_ph = clean_phone(call[0][0])
                msg = call[0][1]
                if to_ph == clean_phone(sales_rep_phone) or to_ph == clean_phone(settings.master_admin_phone):
                    if "PENDING BALANCE ADJUSTMENT" in msg and "150.57" in msg:
                        rep_notified = True
            assert rep_notified is True, "Sales Rep should receive pending balance notification"
            print("[PASS] Sales Representative notified of pending balance addition.")

            # 3. Sales Admin confirmation & Close Trip button check
            call_kwargs = mock_btn.call_args[1]
            body = call_kwargs.get("body_text", "")
            assert "FAVLOGIX UPDATE CONFIRMED" in body
            assert "800.00" in body
            buttons = call_kwargs.get("buttons", [])
            assert any(b.get("id") == f"flt_adm_close_{test_trip_id}" for b in buttons), "Should provide Close Trip button"
            print("[PASS] Sales Admin confirmed update and received [Close Trip] button.")

            # 4. Trip status check in DB
            trip_check = await get_fleet_trip_request_by_id(s, test_trip_id)
            assert trip_check.status == "BALANCED"
            assert trip_check.discrepancy_amount == 150.57
            print("[PASS] Trip marked BALANCED in database.")

    # ------------------------------------------------------------------------
    # TEST CASE 8: Sales Admin clicks [Close Trip] -> Trip Officially CLOSED
    # ------------------------------------------------------------------------
    print("\n--- TEST CASE 8: CLOSE TRIP FINALIZATION ---")
    with patch("app.meta_api.meta_api.send_text_message", new_callable=AsyncMock) as mock_txt:
        async with async_session_factory() as s:
            handled = await handle_sales_admin_interaction(s, admin_phone, f"flt_adm_close_{test_trip_id}", None)
            assert handled is True
            trip_check = await get_fleet_trip_request_by_id(s, test_trip_id)
            assert trip_check.status == "CLOSED"
            print("[PASS] Trip officially closed by Sales Admin.")

    # Cleanup test data
    async with async_session_factory() as s:
        await s.execute(delete(FleetTripRequest).where(FleetTripRequest.trip_id == test_trip_id))
        await s.execute(delete(FleetCustomerSchedule).where(FleetCustomerSchedule.trip_id == test_trip_id))
        await s.execute(delete(FleetPendingLedger).where(FleetPendingLedger.trip_id == test_trip_id))
        await s.commit()

    print("\n[SUCCESS] ALL SALES ADMIN BALANCING & RECONCILIATION TESTS PASSED PERFECTLY!")

if __name__ == "__main__":
    asyncio.run(run_tests())
