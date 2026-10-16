import asyncio
import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.database import (
    async_session_factory,
    init_db_models,
    record_pending_ledger_entry,
    get_sales_rep_pending_balance,
    get_emergency_expense_by_id,
    record_emergency_expense,
    create_or_update_fleet_trip_request,
    FleetTripRequest,
    FleetEmergencyExpense,
    FleetPendingLedger,
)
from app.state_manager import get_user_state, set_user_state, clear_user_state
from app.handlers.driver_handler import handle_driver_interaction
from app.handlers.fleet_approval_handler import handle_fleet_approval_flow
from app.meta_api import meta_api


async def test_full_flow():
    print("=== STARTING FULL TEST SUITE FOR MULTI-COMPANY PACKAGING LIST & EXTRA ALLOWANCE ===")


    # Track outgoing messages
    sent_messages = []
    original_send_text = meta_api.send_text_message
    original_send_button = meta_api.send_button_message

    async def mock_send_text(to_phone, body_text):
        sent_messages.append({"type": "text", "to": to_phone, "body": body_text})
        return {"status": "success"}

    async def mock_send_button(to_phone, body_text, buttons, header_text=""):
        sent_messages.append({"type": "button", "to": to_phone, "body": body_text, "buttons": buttons, "header": header_text})
        return {"status": "success"}

    meta_api.send_text_message = mock_send_text
    meta_api.send_button_message = mock_send_button

    test_driver_phone = "263771112233"
    test_sales_phone = "263718643451" # Stuart Chaleka (TG Rep)
    test_manager_phone = "263772223344" # Zayn / Approver
    trip_id = "TEST-TRIP-999"

    async with async_session_factory() as session:
        # 1. Setup mock trip in database
        trip = await create_or_update_fleet_trip_request(
            session=session,
            trip_id=trip_id,
            company_name="Tagoneswa Hardware",
            salesperson_phone=test_sales_phone,
            destination_city="Bindura",
            salesperson_name="Stuart Chaleka"
        )
        trip.driver_phone = test_driver_phone
        trip.driver_name = "Tinashe Driver"
        trip.truck_plate = "AEZ 9999"
        trip.status = "ACTIVE"
        await session.commit()
        await clear_user_state(session, test_driver_phone)
        await clear_user_state(session, test_sales_phone)

        # ==========================================
        # TEST 1: Driver Extra Allowance Flow
        # ==========================================
        print("\n--- Test 1.1: Driver clicks Extra Allowance ---")
        sent_messages.clear()
        handled = await handle_driver_interaction(
            session=session,
            phone=test_driver_phone,
            message_text=f"flt_drv_allow_{trip_id}",
            state=None
        )
        assert handled is True
        assert any("EXTRA ALLOWANCE" in m.get("body", "") and "Reason" in m.get("body", "") for m in sent_messages)
        print("[OK] Prompted for Reason successfully.")

        # Test 1.2: Driver enters Reason
        print("\n--- Test 1.2: Driver enters Reason ---")
        st = await get_user_state(session, test_driver_phone)
        sent_messages.clear()
        handled = await handle_driver_interaction(
            session=session,
            phone=test_driver_phone,
            message_text="Bridge detour due to heavy rain and road repair",
            state=st
        )
        assert handled is True
        assert any("accommodation" in m.get("body", "").lower() for m in sent_messages)
        print("[OK] Reason saved; accommodation Yes/No buttons presented.")

        # Test 1.3: Driver clicks Yes for Accommodation
        print("\n--- Test 1.3: Driver clicks Yes for Accommodation ---")
        st = await get_user_state(session, test_driver_phone)
        sent_messages.clear()
        handled = await handle_driver_interaction(
            session=session,
            phone=test_driver_phone,
            message_text=f"flt_alw_ac_y_{trip_id}",
            state=st
        )
        assert handled is True
        assert any("accommodation allowance amount" in m.get("body", "").lower() for m in sent_messages)
        print("[OK] Accommodation amount prompt received.")

        # Test 1.4: Driver enters Accommodation Amount ($35.00)
        print("\n--- Test 1.4: Driver enters Accommodation Amount ($35.00) ---")
        st = await get_user_state(session, test_driver_phone)
        sent_messages.clear()
        handled = await handle_driver_interaction(
            session=session,
            phone=test_driver_phone,
            message_text="35.00",
            state=st
        )
        assert handled is True
        assert any("food" in m.get("body", "").lower() for m in sent_messages)
        print("[OK] Accommodation amount $35.00 saved; food Yes/No buttons presented.")

        # Test 1.5: Driver clicks Yes for Food
        print("\n--- Test 1.5: Driver clicks Yes for Food ---")
        st = await get_user_state(session, test_driver_phone)
        sent_messages.clear()
        handled = await handle_driver_interaction(
            session=session,
            phone=test_driver_phone,
            message_text=f"flt_alw_fd_y_{trip_id}",
            state=st
        )
        assert handled is True
        assert any("food allowance amount" in m.get("body", "").lower() for m in sent_messages)
        print("[OK] Food amount prompt received.")

        # Test 1.6: Driver enters Food Amount ($20.00)
        print("\n--- Test 1.6: Driver enters Food Amount ($20.00) ---")
        st = await get_user_state(session, test_driver_phone)
        sent_messages.clear()
        handled = await handle_driver_interaction(
            session=session,
            phone=test_driver_phone,
            message_text="20.00",
            state=st
        )
        assert handled is True
        # Must show summary with Accommodation $35.00, Food $20.00, Total $55.00
        summary_msg = next((m for m in sent_messages if "EXTRA ALLOWANCE SUMMARY" in m.get("body", "")), None)
        assert summary_msg is not None
        assert "$35.00" in summary_msg["body"]
        assert "$20.00" in summary_msg["body"]
        assert "$55.00" in summary_msg["body"]
        print("[OK] Summary card verified: Accom $35.00 + Food $20.00 = Total $55.00.")

        # Test 1.7: Driver clicks Submit for Approval
        print("\n--- Test 1.7: Driver clicks Submit for Approval ---")
        st = await get_user_state(session, test_driver_phone)
        sent_messages.clear()
        handled = await handle_driver_interaction(
            session=session,
            phone=test_driver_phone,
            message_text=f"flt_alw_submit_{trip_id}",
            state=st
        )
        assert handled is True
        # Verify approval card dispatched to manager
        mgr_card = next((m for m in sent_messages if "EXTRA ALLOWANCE APPROVAL REQUIRED" in m.get("body", "")), None)
        assert mgr_card is not None
        btn_appr = next((b for b in mgr_card["buttons"] if b["id"].startswith("flt_emg_appr_")), None)
        assert btn_appr is not None
        exp_id = int(btn_appr["id"].replace("flt_emg_appr_", ""))
        print(f"[OK] Approval request dispatched with expense ID #{exp_id}.")

        # ==========================================
        # TEST 2: Manager Approves Extra Allowance
        # ==========================================
        print("\n--- Test 2: Manager Approves Extra Allowance ---")
        initial_rep_pending = await get_sales_rep_pending_balance(session, test_sales_phone)
        print(f"Sales Rep Initial Pending Balance: ${initial_rep_pending:,.2f}")

        sent_messages.clear()
        handled = await handle_driver_interaction(
            session=session,
            phone=test_manager_phone,
            message_text=f"flt_emg_appr_{exp_id}",
            state=None
        )
        assert handled is True

        # Check driver got approval
        drv_note = next((m for m in sent_messages if m["to"] == test_driver_phone and "EXTRA ALLOWANCE APPROVED" in m["body"]), None)
        assert drv_note is not None
        print("[OK] Driver received approval confirmation.")

        # Check accounts received notification
        acc_note = next((m for m in sent_messages if "EXTRA ALLOWANCE APPROVED" in m.get("body", "") and "Harare Hub" in m.get("body", "")), None)
        assert acc_note is not None
        print("[OK] Accounts received disbursement alert.")

        # Check Sales Admin received notification
        sa_note = next((m for m in sent_messages if "FLEET EXPENSE UPDATE" in m.get("body", "") and "EXTRA ALLOWANCE APPROVED" in m.get("body", "")), None)
        assert sa_note is not None
        print("[OK] Sales Admin received approval notification with trip details, approver & amount.")

        # Check Sales Rep pending ledger updated
        new_rep_pending = await get_sales_rep_pending_balance(session, test_sales_phone)
        print(f"Sales Rep New Pending Balance: ${new_rep_pending:,.2f}")
        assert round(new_rep_pending - initial_rep_pending, 2) == 55.00
        print("[OK] Sales Rep pending ledger credited with +$55.00 extra allowance.")

        # Check Sales Rep received WhatsApp notice
        rep_note = next((m for m in sent_messages if m["to"] == test_sales_phone and "EXTRA ALLOWANCE CHARGED TO PENDING" in m["body"]), None)
        assert rep_note is not None
        print("[OK] Sales Rep notified of updated pending recovery balance.")

        # ==========================================
        # TEST 3: Multi-Company Packaging List Flow
        # ==========================================
        print("\n--- Test 3.1: Multi-Company Packaging List [No] Path ---")
        await clear_user_state(session, test_sales_phone)
        # Simulate state right after 1st trip data retrieved: awaiting_multico_decision
        await set_user_state(
            session=session,
            phone=test_sales_phone,
            current_step="awaiting_multico_decision",
            current_data={
                "trip_id": "TRIP-TG-001",
                "company_name": "Tagoneswa Hardware",
                "destination_city": "Bindura",
                "sales_amount": 1200.0,
                "raw_trip_data": {"trip_id": "TRIP-TG-001", "total_amount": 1200.0, "destination_city": "Bindura"}
            },
            flow_name="fleet_approval"
        )
        st = await get_user_state(session, test_sales_phone)
        sent_messages.clear()
        handled = await handle_fleet_approval_flow(
            session=session,
            phone=test_sales_phone,
            employee=None,
            message_text="flt_pkg_multico_no",
            state=st
        )
        assert handled is True
        wh_msg = next((m for m in sent_messages if "DEPARTURE WAREHOUSE" in m.get("body", "")), None)
        assert wh_msg is not None
        print("[OK] Clicking [No] continues directly to Departure Warehouse selection.")

        print("\n--- Test 3.2: Multi-Company Packaging List [Yes] Path ---")
        await set_user_state(
            session=session,
            phone=test_sales_phone,
            current_step="awaiting_multico_decision",
            current_data={
                "trip_id": "TRIP-TG-001",
                "company_name": "Tagoneswa Hardware",
                "destination_city": "Bindura",
                "sales_amount": 1200.0,
                "raw_trip_data": {"trip_id": "TRIP-TG-001", "total_amount": 1200.0, "destination_city": "Bindura"}
            },
            flow_name="fleet_approval"
        )
        st = await get_user_state(session, test_sales_phone)
        sent_messages.clear()
        handled = await handle_fleet_approval_flow(
            session=session,
            phone=test_sales_phone,
            employee=None,
            message_text="flt_pkg_multico_yes",
            state=st
        )
        assert handled is True
        co_msg = next((m for m in sent_messages if "SECOND PACKAGING LIST" in m.get("body", "")), None)
        assert co_msg is not None
        # Check buttons are Tagoneswa and LG Plast
        co_btns = [b["id"] for b in co_msg["buttons"]]
        assert "flt_pkg_co_tg" in co_btns and "flt_pkg_co_lg" in co_btns
        print("[OK] Clicking [Yes] asks to select company for 2nd packaging list (Tagoneswa vs LG Plast).")

        # Test selecting 2nd company: LG Plast
        print("\n--- Test 3.3: Select LG Plast for 2nd Packaging List ---")
        st = await get_user_state(session, test_sales_phone)
        sent_messages.clear()
        handled = await handle_fleet_approval_flow(
            session=session,
            phone=test_sales_phone,
            employee=None,
            message_text="flt_pkg_co_lg",
            state=st
        )
        assert handled is True
        trip2_msg = next((m for m in sent_messages if "ENTER 2ND TRIP ID" in m.get("body", "") and "LG Plast" in m.get("body", "")), None)
        assert trip2_msg is not None
        print("[OK] Prompts for 2nd Trip ID for LG Plast.")

    print("\n[SUCCESS] ALL TESTS PASSED SUCCESSFULLY! Both flows operating exactly as requested!")

if __name__ == "__main__":
    asyncio.run(test_full_flow())
