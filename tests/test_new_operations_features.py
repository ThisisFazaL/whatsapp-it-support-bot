import asyncio
import os
import sys
import unittest
from unittest.mock import patch, AsyncMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_fleet.db"

from sqlalchemy import delete, select
from app.config import settings
from app.database import (
    async_session_factory, init_db_models,
    FleetTripRequest, FleetCustomerSchedule, FleetEmergencyExpense, DriverPendingLedger,
    FleetTripApproval, FleetPendingLedger,
    get_fleet_trip_request_by_id, get_active_trip_for_driver, get_customer_schedules_for_trip,
    get_emergency_expenses_for_trip, get_sales_rep_pending_balance
)
from app.workshop.models import WorkshopStaff
from app.state_manager import get_user_state, set_user_state, clear_user_state
from app.handlers.fleet_approval_handler import handle_fleet_approval_flow, notify_sales_rep_allowance_entry
from app.handlers.logistics_handler import handle_edward_interaction, resolve_driver_phone
from app.handlers.zayn_accounts_handler import handle_zayn_accounts_interaction, notify_zayn_allowance_approval
from app.handlers.driver_handler import handle_driver_interaction
from app.services.allowance_calculator import (
    calculate_total_allowance, calculate_meal_count, calculate_accommodation, is_masvingo_route
)
from app.services.trip_verification_service import trip_verification_service


class TestNewOperationsFeatures(unittest.IsolatedAsyncioTestCase):
    _db_initialized = False

    async def asyncSetUp(self):
        if not TestNewOperationsFeatures._db_initialized:
            await init_db_models()
            TestNewOperationsFeatures._db_initialized = True
        self.sales_rep_phone = "263772111222"
        self.edward_phone = settings.edward_phone
        self.zayn_phone = settings.zayn_phone
        self.accounts_phone = settings.accounts_phones[0]
        self.driver_phone = "263788112771"

        async with async_session_factory() as session:
            for model in [FleetEmergencyExpense, FleetCustomerSchedule, DriverPendingLedger, FleetTripRequest, FleetTripApproval, FleetPendingLedger]:
                await session.execute(delete(model))
            await session.commit()

            # Ensure WorkshopStaff driver
            st_chk = await session.execute(select(WorkshopStaff).where(WorkshopStaff.phone == self.driver_phone))
            if not st_chk.scalars().first():
                ws = WorkshopStaff(
                    phone=self.driver_phone,
                    full_name="Terrence Mupfumi",
                    role="Driver",
                    active=True
                )
                session.add(ws)
                await session.commit()

    def test_allowance_calculator_rules(self):
        """Tests meal timing, rates ($2), and Masvingo warehouse accommodation rule."""
        # 1. Departure at 2:00 PM (14:00) -> Lunch strictly EXCLUDED
        meals_2pm = calculate_meal_count("2:00 PM", "08:00 PM")
        self.assertEqual(meals_2pm, 1)  # Only dinner included

        # 2. Early morning departure 06:30 AM returning 08:00 PM -> 3 meals
        meals_full = calculate_meal_count("06:30 AM", "08:00 PM")
        self.assertEqual(meals_full, 3)

        # 3. Masvingo route accommodation -> $0.00 (Tagoneswa warehouse rule)
        self.assertTrue(is_masvingo_route("Harare - Masvingo Highway"))
        self.assertTrue(is_masvingo_route("Maswingo"))
        accom_msv = calculate_accommodation("Masvingo Depot", nights=2, crew_count=3)
        self.assertEqual(accom_msv["cost"], 0.0)
        self.assertTrue(accom_msv["has_warehouse_stay"])

        # 4. Non-Masvingo route accommodation -> $15/person/night
        accom_byo = calculate_accommodation("Bulawayo Depot", nights=2, crew_count=2)
        self.assertEqual(accom_byo["cost"], 60.0)  # 2 nights * 2 people * $15 = $60
        self.assertFalse(accom_byo["has_warehouse_stay"])

        # 5. Full allowance coordination
        b_msv = calculate_total_allowance(
            crew_count=2,
            departure_str="06:30 AM",
            return_str="tomorrow 08:00 PM",
            route_or_city="Masvingo",
            toll_cost=20.0
        )
        # 2 people, 1 night in Masvingo ($0 accom), meals = 6 meals per person ($12 per person * 2 = $24)
        self.assertEqual(b_msv["accommodation_cost"], 0.0)
        self.assertEqual(b_msv["toll_cost"], 20.0)
        self.assertEqual(b_msv["food_allowance"], b_msv["meal_count_per_person"] * 2 * 2.0)

    @patch("app.meta_api.meta_api.send_text_message", new_callable=AsyncMock)
    @patch("app.meta_api.meta_api.send_button_message", new_callable=AsyncMock)
    async def test_packaging_list_deficit_and_pending_balance(self, mock_send_btn, mock_send_txt):
        """Tests packaging list verification when deficit is detected and added to pending balance."""
        async with async_session_factory() as session:
            trip_id = "TRIP-DEFICIT-001"
            # Setup state at awaiting_favlogix_charged
            data = {
                "trip_id": trip_id,
                "clean_btn_id": trip_id,
                "required_charge": 100.0,
                "company_name": "A. TG Hardware",
                "dest": "Mutare",
                "route": "Mutare",
                "sales_val": 15000.0
            }
            await set_user_state(session, self.sales_rep_phone, "awaiting_favlogix_charged", data, flow_name="fleet_approval")

            # Sales rep clicks YES
            state = await get_user_state(session, self.sales_rep_phone)
            handled = await handle_fleet_approval_flow(session, self.sales_rep_phone, None, f"flt_chg_yes_{trip_id}", state)
            self.assertTrue(handled)

            # Prompts for Transport Charge ID
            prompt = mock_send_txt.call_args[0][1]
            self.assertIn("TRANSPORT CHARGE ID", prompt)

            # Sales Rep enters a TC ID that causes a deficit (e.g. 'mtrtc_deficit')
            state = await get_user_state(session, self.sales_rep_phone)
            handled = await handle_fleet_approval_flow(session, self.sales_rep_phone, None, "mtrtc_deficit", state)
            self.assertTrue(handled)

            # Deficit warning card sent with Update in ERP and Add to Pending buttons
            deficit_card = mock_send_btn.call_args[1]["body_text"]
            self.assertIn("DEFICIT DETECTED", deficit_card)
            self.assertIn("Missing Amount: *$60.00*", deficit_card)
            btns = [b["title"] for b in mock_send_btn.call_args[1]["buttons"]]
            self.assertEqual(btns, ["Update in ERP", "Add to Pending"])

            # Sales Rep clicks [Add to Pending]
            state = await get_user_state(session, self.sales_rep_phone)
            handled = await handle_fleet_approval_flow(session, self.sales_rep_phone, None, f"flt_tc_pend_{trip_id}", state)
            self.assertTrue(handled)

            # Check that pending balance was recorded
            bal = await get_sales_rep_pending_balance(session, self.sales_rep_phone)
            self.assertEqual(bal, 60.0)

            # Check trip request created and cleared for dispatch
            req = await get_fleet_trip_request_by_id(session, trip_id)
            self.assertIsNotNone(req)

    @patch("app.meta_api.meta_api.send_text_message", new_callable=AsyncMock)
    @patch("app.meta_api.meta_api.send_button_message", new_callable=AsyncMock)
    async def test_driver_numbered_customer_selection(self, mock_send_btn, mock_send_txt):
        """Tests that driver selecting delivery charges gets a numbered list and replying 2 selects Customer 2."""
        async with async_session_factory() as session:
            trip_id = "TRIP-SELECT-002"
            from app.database import create_or_update_fleet_trip_request, save_customer_schedules_batch
            await create_or_update_fleet_trip_request(
                session, trip_id, "A. TG Hardware", self.sales_rep_phone, "Gweru", "Sales", None, "Gweru", 10000.0, 150.0
            )
            # Create 3 customers
            schedules = [
                {"customer_id": "CUST-A", "reference_note": "Alpha Hardware", "expected_charge": 50.0},
                {"customer_id": "CUST-B", "reference_note": "Beta Depot", "expected_charge": 60.0},
                {"customer_id": "CUST-C", "reference_note": "Gamma Timber", "expected_charge": 40.0}
            ]
            await save_customer_schedules_batch(session, trip_id, schedules)

            # Driver clicks Delivery Charges
            handled = await handle_driver_interaction(session, self.driver_phone, f"flt_drv_deliv_{trip_id}", None)
            self.assertTrue(handled)

            # Verify prompt lists all 3 customers numbered
            prompt = mock_send_txt.call_args[0][1]
            self.assertIn("1️⃣ *Alpha Hardware (CUST-A)*", prompt)
            self.assertIn("2️⃣ *Beta Depot (CUST-B)*", prompt)
            self.assertIn("3️⃣ *Gamma Timber (CUST-C)*", prompt)

            # Driver replies '2' to select Beta Depot
            state = await get_user_state(session, self.driver_phone)
            self.assertEqual(state.current_step, "awaiting_customer_number")
            handled = await handle_driver_interaction(session, self.driver_phone, "2", state)
            self.assertTrue(handled)

            # Verify customer Beta Depot selected and expected charge is hidden
            next_prompt = mock_send_txt.call_args[0][1]
            self.assertIn("Beta Depot", next_prompt)
            self.assertNotIn("60.00", next_prompt)  # Blind entry!
            self.assertNotIn("Expected", next_prompt)

            # Driver enters collected amount: 60.00
            state = await get_user_state(session, self.driver_phone)
            self.assertEqual(state.current_step, "awaiting_collected_amount")
            handled = await handle_driver_interaction(session, self.driver_phone, "60.00", state)
            self.assertTrue(handled)

            # Driver selects payment method CASH
            state = await get_user_state(session, self.driver_phone)
            handled = await handle_driver_interaction(session, self.driver_phone, f"flt_pay_cash_{trip_id}", state)
            self.assertTrue(handled)

            # Verify CUST-B is updated and MATCHED
            custs = await get_customer_schedules_for_trip(session, trip_id)
            cust_b = next(c for c in custs if c.customer_id == "CUST-B")
            self.assertEqual(cust_b.collected_charge, 60.0)
            self.assertEqual(cust_b.status, "MATCHED")


if __name__ == "__main__":
    unittest.main()
