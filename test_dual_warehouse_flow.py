import asyncio
import os

os.environ["ENVIRONMENT"] = "development"

from app.database import (
    async_session_factory, init_db_models, FleetTripApproval, FleetTripRequest, Employee, ConversationState
)
from app.services.trip_pricing_service import (
    calculate_trip_approval, get_city_minimum, MASVINGO_CORRIDORS, MASTER_CORRIDORS,
    normalize_warehouse_name
)
from app.services.trip_verification_service import trip_verification_service
from app.handlers.fleet_approval_handler import handle_fleet_approval_flow, set_solo_test_mode
from app.handlers.logistics_handler import notify_edward_new_trip
from app.state_manager import get_user_state, clear_user_state
from sqlalchemy import select, delete


async def run_tests():
    print("==================================================================")
    print("TESTING DUAL WAREHOUSE ARCHITECTURE (HARARE & MASVINGO HUBS)")
    print("==================================================================")

    # 1. Test normalize_warehouse_name
    print("\n--- Test 1: Warehouse Normalization ---")
    assert normalize_warehouse_name("Harare") == "Harare"
    assert normalize_warehouse_name("harare warehouse") == "Harare"
    assert normalize_warehouse_name("Masvingo") == "Masvingo"
    assert normalize_warehouse_name("flt_wh_masvingo") == "Masvingo"
    assert normalize_warehouse_name("mvg") == "Masvingo"
    assert normalize_warehouse_name(None) == "Harare"
    print("[PASS] Warehouse normalization works accurately")

    # 2. Test Pricing Comparisons: Harare vs Masvingo
    print("\n--- Test 2: Pricing Comparison (Chiredzi, Zaka, Bulawayo) ---")
    # From Harare:
    h_chiredzi = calculate_trip_approval(actual_sales=10000.0, destination="Chiredzi", origin_warehouse="Harare")
    assert h_chiredzi["distance_km"] == 438.0
    assert h_chiredzi["required_minimum"] == 16243.75
    assert h_chiredzi["approved"] is False
    assert h_chiredzi["origin_warehouse"] == "Harare"
    assert "Route 6" in h_chiredzi["route"]
    print(f"[PASS] Harare -> Chiredzi: {h_chiredzi['distance_km']} km, min sales: ${h_chiredzi['required_minimum']:,.2f} ({h_chiredzi['route']})")

    # From Masvingo:
    m_chiredzi = calculate_trip_approval(actual_sales=10000.0, destination="Chiredzi", origin_warehouse="Masvingo")
    assert m_chiredzi["distance_km"] == 156.0
    assert m_chiredzi["required_minimum"] == 5900.00
    assert m_chiredzi["approved"] is True  # $10k > $5.9k!
    assert m_chiredzi["origin_warehouse"] == "Masvingo"
    assert "Route M1" in m_chiredzi["route"]
    print(f"[PASS] Masvingo -> Chiredzi: {m_chiredzi['distance_km']} km, min sales: ${m_chiredzi['required_minimum']:,.2f} ({m_chiredzi['route']}) -> APPROVED!")

    # From Masvingo -> Zaka
    m_zaka = calculate_trip_approval(actual_sales=4000.0, destination="Zaka", origin_warehouse="Masvingo")
    assert m_zaka["distance_km"] == 86.0
    assert m_zaka["required_minimum"] == 3750.00
    assert m_zaka["approved"] is True
    print(f"[PASS] Masvingo -> Zaka: {m_zaka['distance_km']} km, min sales: ${m_zaka['required_minimum']:,.2f} ({m_zaka['route']})")

    # From Masvingo -> Local
    m_local = calculate_trip_approval(actual_sales=3000.0, destination="Masvingo", origin_warehouse="Masvingo")
    assert m_local["distance_km"] == 5.0
    assert m_local["required_minimum"] == 2201.56
    assert m_local["approved"] is True
    print(f"[PASS] Masvingo -> Local: {m_local['distance_km']} km, min sales: ${m_local['required_minimum']:,.2f} ({m_local['route']})")

    # 3. Test Database Init & Schema Migration
    print("\n--- Test 3: Database Schema Migration ---")
    await init_db_models()
    print("[PASS] init_db_models executed successfully with origin_warehouse columns")

    # 4. End-to-End Chatbot WhatsApp Interaction Test
    print("\n--- Test 4: End-to-End WhatsApp Chatbot Interaction ---")
    set_solo_test_mode(True)
    test_phone = "263772111222"
    test_trip_id = "06102026-CHIREDZI"

    from unittest.mock import patch, AsyncMock
    from app.meta_api import meta_api

    mock_raw = {
        "success": True,
        "raw_data": {
            "trip_id": test_trip_id,
            "destination_city": "Chiredzi",
            "total_amount": 10000.0,
            "company_name": "A. TG Hardware",
            "customers": [{"customer_name": "Lowveld Supplies", "order_id": "ORD-001", "total": 10000.0, "to_collect": 0.0}]
        }
    }

    p1 = patch.object(trip_verification_service, "fetch_raw_trip_data", new=AsyncMock(return_value=mock_raw))
    p2 = patch.object(meta_api, "send_text_message", new=AsyncMock(return_value=True))
    p3 = patch.object(meta_api, "send_button_message", new=AsyncMock(return_value=True))
    p1.start()
    p2.start()
    p3.start()

    async with async_session_factory() as session:
        # Clean up any leftover test data
        await session.execute(delete(FleetTripRequest).where(FleetTripRequest.trip_id == test_trip_id))
        await session.execute(delete(FleetTripApproval).where(FleetTripApproval.trip_id == test_trip_id))
        await session.commit()
        await clear_user_state(session, test_phone)

        # Mock an employee
        emp = Employee(
            full_name="Tariro Sales Rep",
            phone=test_phone,
            active=True
        )

        # Step A: User initiates fleet approval
        st = await get_user_state(session, test_phone)
        await handle_fleet_approval_flow(session, test_phone, emp, "1", st)
        st = await get_user_state(session, test_phone)
        assert st.current_step == "awaiting_trip_id"
        print("[PASS] Step A: Bot requests Trip ID")

        # Step B: User enters trip ID for Chiredzi
        handled = await handle_fleet_approval_flow(session, test_phone, emp, test_trip_id, st)
        assert handled is True
        st = await get_user_state(session, test_phone)
        assert st.current_step == "awaiting_warehouse_selection", f"Expected awaiting_warehouse_selection, got {st.current_step}"
        assert st.current_data.get("trip_id") == test_trip_id
        print("[PASS] Step B: Bot asks sales rep to select departure warehouse (Harare vs Masvingo)")

        # Step C: Sales rep selects Masvingo Warehouse button
        handled_wh = await handle_fleet_approval_flow(session, test_phone, emp, "flt_wh_masvingo", st)
        assert handled_wh is True
        st = await get_user_state(session, test_phone)
        assert st.current_data.get("origin_warehouse") == "Masvingo"
        print("[PASS] Step C: Bot calculates pricing with Masvingo origin and presents trip details")

        # Verify FleetTripApproval has origin_warehouse = Masvingo
        app_res = await session.execute(
            select(FleetTripApproval).where(FleetTripApproval.trip_id == test_trip_id).order_by(FleetTripApproval.id.desc())
        )
        app_obj = app_res.scalars().first()
        assert app_obj is not None
        assert app_obj.origin_warehouse == "Masvingo"
        print(f"[PASS] Step D: FleetTripApproval record created with origin_warehouse={app_obj.origin_warehouse}")

        # Step E: User clicks Authorize Dispatch
        clean_id = test_trip_id.replace("-", "").upper()
        handled_disp = await handle_fleet_approval_flow(session, test_phone, emp, f"flt_disp_ok_{test_trip_id}", st)
        assert handled_disp is True

        # Verify FleetTripRequest has origin_warehouse = Masvingo
        req_res = await session.execute(
            select(FleetTripRequest).where(FleetTripRequest.trip_id == test_trip_id)
        )
        req_obj = req_res.scalars().first()
        assert req_obj is not None
        assert req_obj.origin_warehouse == "Masvingo"
        print(f"[PASS] Step E: FleetTripRequest created with origin_warehouse={req_obj.origin_warehouse}")

        # Clean up test trip
        await session.execute(delete(FleetTripRequest).where(FleetTripRequest.trip_id == test_trip_id))
        await session.execute(delete(FleetTripApproval).where(FleetTripApproval.trip_id == test_trip_id))
        await session.commit()
        await clear_user_state(session, test_phone)
        print("[PASS] Test cleanup completed")

    p1.stop()
    p2.stop()
    p3.stop()

    print("\n==================================================================")
    print("ALL DUAL WAREHOUSE TESTS PASSED WITH 100% SUCCESS!")
    print("==================================================================")


if __name__ == "__main__":
    asyncio.run(run_tests())
