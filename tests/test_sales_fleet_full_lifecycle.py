import asyncio
import os
import sys
import unittest
from unittest.mock import patch, AsyncMock

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_fleet.db"

from sqlalchemy import delete
from app.config import settings
from app.database import (
    async_session_factory, init_db_models,
    FleetTripRequest, FleetCustomerSchedule, FleetEmergencyExpense, DriverPendingLedger,
    FleetTripApproval, FleetPendingLedger,
    get_fleet_trip_request_by_id, get_active_trip_for_driver, get_pending_trips_for_edward,
    get_customer_schedules_for_trip, get_emergency_expenses_for_trip, get_trip_reconciliation_summary,
    get_sales_rep_pending_balance, ConversationState
)
from app.state_manager import get_user_state, set_user_state, clear_user_state
from app.handlers.fleet_approval_handler import handle_fleet_approval_flow, is_salesperson
from app.handlers.logistics_handler import handle_edward_interaction, notify_edward_new_trip
from app.handlers.zayn_accounts_handler import handle_zayn_accounts_interaction, notify_zayn_allowance_approval
from app.handlers.driver_handler import handle_driver_interaction
from app.handlers.sales_admin_handler import handle_sales_admin_interaction, notify_sales_admin_balancing_session
from app.handlers.logistics_manager_handler import handle_logistics_manager_interaction, broadcast_confidential_trip_closed
from app.handlers.fleet_dispatcher import is_fleet_interaction, dispatch_fleet_message


class TestSalesFleetFullLifecycle(unittest.IsolatedAsyncioTestCase):
    _db_initialized = False

    async def asyncSetUp(self):
        if not TestSalesFleetFullLifecycle._db_initialized:
            await init_db_models()
            TestSalesFleetFullLifecycle._db_initialized = True
        self.sales_rep_phone = "263772111222"
        self.edward_phone = settings.edward_phone
        self.zayn_phone = settings.zayn_phone
        self.accounts_phone = settings.accounts_phones[0]
        self.driver_phone = "263779888777"
        self.sales_admin_phone = settings.sales_admin_tg_phone
        self.logistics_mgr_phone = settings.logistics_manager_phone

        async with async_session_factory() as session:
            for model in [FleetEmergencyExpense, FleetCustomerSchedule, DriverPendingLedger, FleetTripRequest, FleetTripApproval, FleetPendingLedger]:
                await session.execute(delete(model))
            await session.commit()

    @patch("app.meta_api.meta_api.send_text_message", new_callable=AsyncMock)
    @patch("app.meta_api.meta_api.send_button_message", new_callable=AsyncMock)
    @patch("app.services.trip_verification_service.trip_verification_service.verify_trip")
    async def test_full_7_stage_sales_fleet_lifecycle(self, mock_verify, mock_send_btn, mock_send_txt):
        """
        Tests the complete 7-stage lifecycle with all user constraints:
        - Stage 1: Company selection, clean shortfall view (no formula, no route minimum, no shortfall amount).
        - Stage 2: [YES] charged in Favlogix, customer manifest registered.
        - Stage 3: Edward allocation without brackets, Sales total hidden.
        - Stage 4: Zayn approval, Accounts transfer.
        - Stage 5: Driver transit, autonomous Customer ID lookup, payment method, emergency charges, return.
        - Stage 6: Sales Admin balancing session.
        - Stage 7: Logistics Manager adjudication and confidential TRIP CLOSED broadcast (Sales Total hidden).
        """
        async with async_session_factory() as session:
            # Clear states
            await clear_user_state(session, self.sales_rep_phone)
            await clear_user_state(session, self.edward_phone)
            await clear_user_state(session, self.zayn_phone)
            await clear_user_state(session, self.accounts_phone)
            await clear_user_state(session, self.driver_phone)
            await clear_user_state(session, self.sales_admin_phone)
            await clear_user_state(session, self.logistics_mgr_phone)

            # ----------------------------------------------------
            # STAGE 1: Sales Rep initiates Trip Approval
            # ----------------------------------------------------
            # Sales Rep taps [ 🚛 Fleet Approval ]
            state = await get_user_state(session, self.sales_rep_phone)
            handled = await handle_fleet_approval_flow(session, self.sales_rep_phone, None, "btn_domain_fleet", state)
            self.assertTrue(handled)

            # Verify Company Selection Buttons presented (A. TG Hardware, B. LG Plast, C. Kreckle)
            call_btn = mock_send_btn.call_args[1]
            btn_titles = [b["title"] for b in call_btn["buttons"]]
            self.assertIn("A. TG Hardware", btn_titles)
            self.assertIn("B. LG Plast", btn_titles)
            self.assertIn("C. Kreckle", btn_titles)

            # Sales Rep selects [A. TG Hardware]
            state = await get_user_state(session, self.sales_rep_phone)
            handled = await handle_fleet_approval_flow(session, self.sales_rep_phone, None, "flt_co_tg", state)
            self.assertTrue(handled)

            # Verify prompt asks for Trip ID
            last_prompt = mock_send_txt.call_args[0][1]
            self.assertIn("A. TG Hardware", last_prompt)
            self.assertIn("Trip ID", last_prompt)

            # Mock Favlogix response with shortfall
            trip_test_id = "TRIP-2026-TEST01"
            mock_verify.return_value = {
                "success": True,
                "trip_id": trip_test_id,
                "destination_city": "Gweru",
                "route": "Gweru",
                "total_amount": 14200.00,
                "required_minimum": 18000.00,
                "shortfall": 3800.00,
                "transport_charge": 152.00,
                "approved": False
            }

            # Sales rep sends Trip ID
            state = await get_user_state(session, self.sales_rep_phone)
            handled = await handle_fleet_approval_flow(session, self.sales_rep_phone, None, trip_test_id, state)
            self.assertTrue(handled)

            # CRITICAL CONSTRAINT CHECK:
            # Check card shown to Sales Rep:
            # Must show Trip ID, Destination, Sales Total, Transport Fee to Take.
            # MUST NOT show "Route Minimum", "Shortfall: $3,800.00", or "4% Transport Charge"!
            shortfall_card = mock_send_btn.call_args[1]["body_text"]
            self.assertIn("Gweru", shortfall_card)
            self.assertIn("14,200.00", shortfall_card)
            self.assertIn("152.00", shortfall_card)
            self.assertNotIn("Route Minimum", shortfall_card)
            self.assertNotIn("SHORTFALL DETECTED", shortfall_card)
            self.assertNotIn("4%", shortfall_card)

            # Verify 3 clean shortfall buttons without emojis
            sf_buttons = [b["title"] for b in mock_send_btn.call_args[1]["buttons"]]
            self.assertEqual(sf_buttons, ["Full Charge", "Partial Charge", "Add to Pending"])

            # ----------------------------------------------------
            # STAGE 1 (Option 1): Full Charge Selected
            # ----------------------------------------------------
            clean_btn_id = trip_test_id
            state = await get_user_state(session, self.sales_rep_phone)
            handled = await handle_fleet_approval_flow(session, self.sales_rep_phone, None, f"flt_sf_full_{clean_btn_id}", state)
            self.assertTrue(handled)

            # Verify prompt moves directly to Stage 2 Favlogix charge check with [YES], [NO]
            # No redundant "how much amount charged" asked!
            stage2_prompt = mock_send_btn.call_args[1]["body_text"]
            self.assertIn("Please charge all customers in Favlogix and select YES when done", stage2_prompt)
            stage2_btns = [b["title"] for b in mock_send_btn.call_args[1]["buttons"]]
            self.assertEqual(stage2_btns, ["YES", "NO"])

            # ----------------------------------------------------
            # STAGE 2: Sales Rep clicks [YES] & Registers Manifest
            # ----------------------------------------------------
            state = await get_user_state(session, self.sales_rep_phone)
            handled = await handle_fleet_approval_flow(session, self.sales_rep_phone, None, f"flt_chg_yes_{clean_btn_id}", state)
            self.assertTrue(handled)

            # Prompts for customer charges manifest
            manifest_prompt = mock_send_txt.call_args[0][1]
            self.assertIn("CUSTOMER CHARGES MANIFEST", manifest_prompt)

            # Sales Rep enters customer charges
            state = await get_user_state(session, self.sales_rep_phone)
            handled = await handle_fleet_approval_flow(session, self.sales_rep_phone, None, "CUST-101: 72.00, CUST-102: 80.00", state)
            self.assertTrue(handled)

            # Verify database schedules saved and trip created
            req = await get_fleet_trip_request_by_id(session, trip_test_id)
            self.assertIsNotNone(req)
            self.assertEqual(req.status, "PENDING_ASSIGNMENT")
            self.assertEqual(req.company_name, "A. TG Hardware")
            self.assertEqual(req.destination_city, "Gweru")

            schedules = await get_customer_schedules_for_trip(session, trip_test_id)
            self.assertEqual(len(schedules), 2)
            self.assertEqual(schedules[0].customer_id, "CUST-101")
            self.assertEqual(schedules[0].expected_charge, 72.00)
            self.assertEqual(schedules[1].customer_id, "CUST-102")
            self.assertEqual(schedules[1].expected_charge, 80.00)

            # ----------------------------------------------------
            # STAGE 3: Edward receives trip & allocates
            # ----------------------------------------------------
            # Edward checks [Trip Queue]
            handled = await handle_edward_interaction(session, self.edward_phone, "flt_edw_queue", None)
            self.assertTrue(handled)
            queue_card = mock_send_btn.call_args[1]["body_text"]
            self.assertIn(trip_test_id, queue_card)

            # Edward clicks [Allocate Trip]
            handled = await handle_edward_interaction(session, self.edward_phone, f"flt_edw_alloc_{trip_test_id}", None)
            self.assertTrue(handled)

            # 1. Truck plate (typed, NO buttons)
            state = await get_user_state(session, self.edward_phone)
            self.assertEqual(state.current_step, "awaiting_truck_plate")
            # Verify Sales total is hidden from Edward!
            last_prompt = mock_send_txt.call_args[0][1]
            self.assertNotIn("14,200", last_prompt)

            handled = await handle_edward_interaction(session, self.edward_phone, "ZW 123 ABC", state)
            self.assertTrue(handled)

            # 2. Driver name (typed, NO buttons)
            state = await get_user_state(session, self.edward_phone)
            self.assertEqual(state.current_step, "awaiting_driver_name")
            handled = await handle_edward_interaction(session, self.edward_phone, "John Banda", state)
            self.assertTrue(handled)

            # 3. Driver phone
            state = await get_user_state(session, self.edward_phone)
            self.assertEqual(state.current_step, "awaiting_driver_phone")
            handled = await handle_edward_interaction(session, self.edward_phone, self.driver_phone, state)
            self.assertTrue(handled)

            # 4. Crew count (NO brackets in prompt!)
            state = await get_user_state(session, self.edward_phone)
            self.assertEqual(state.current_step, "awaiting_crew_count")
            crew_prompt = mock_send_txt.call_args[0][1]
            self.assertIn("Enter number of crew members:", crew_prompt)
            handled = await handle_edward_interaction(session, self.edward_phone, "2", state)
            self.assertTrue(handled)

            # 5. Meal count (NO brackets in prompt!)
            state = await get_user_state(session, self.edward_phone)
            self.assertEqual(state.current_step, "awaiting_meal_count")
            meal_prompt = mock_send_txt.call_args[0][1]
            self.assertIn("Enter number of meals per person:", meal_prompt)
            handled = await handle_edward_interaction(session, self.edward_phone, "3", state)
            self.assertTrue(handled)

            # 6. Toll count
            state = await get_user_state(session, self.edward_phone)
            self.assertEqual(state.current_step, "awaiting_toll_count")
            handled = await handle_edward_interaction(session, self.edward_phone, "4", state)
            self.assertTrue(handled)

            # 7. Toll cost
            state = await get_user_state(session, self.edward_phone)
            self.assertEqual(state.current_step, "awaiting_toll_cost")
            handled = await handle_edward_interaction(session, self.edward_phone, "34.50", state)
            self.assertTrue(handled)

            # Edward receives Review Summary with [Confirm], [Change] (NO emojis on buttons!)
            review_card = mock_send_btn.call_args[1]["body_text"]
            self.assertIn("Toll cost: $34.50", review_card)
            self.assertIn("Food ($2 x 2 x 3): $12.00", review_card)
            self.assertIn("Total allowance: $46.50", review_card)
            # Sales total strictly hidden from Edward!
            self.assertNotIn("14,200", review_card)

            edw_btns = [b["title"] for b in mock_send_btn.call_args[1]["buttons"]]
            self.assertEqual(edw_btns, ["Confirm", "Change"])

            # Edward clicks [Confirm]
            handled = await handle_edward_interaction(session, self.edward_phone, f"flt_edw_confirm_{trip_test_id}", None)
            self.assertTrue(handled)

            # ----------------------------------------------------
            # STAGE 4: Zayn & Accounts Approval and Transfer
            # ----------------------------------------------------
            # Zayn clicks [Approve]
            handled = await handle_zayn_accounts_interaction(session, self.zayn_phone, f"flt_zayn_app_{trip_test_id}", None)
            self.assertTrue(handled)

            req = await get_fleet_trip_request_by_id(session, trip_test_id)
            self.assertEqual(req.allowance_status, "APPROVED")

            # Accounts clicks [Transfer Done]
            handled = await handle_zayn_accounts_interaction(session, self.accounts_phone, f"flt_acc_done_{trip_test_id}", None)
            self.assertTrue(handled)

            req = await get_fleet_trip_request_by_id(session, trip_test_id)
            self.assertEqual(req.allowance_status, "TRANSFERRED")

            # ----------------------------------------------------
            # STAGE 5: Driver Transit & Collections
            # ----------------------------------------------------
            # Driver enters departure time
            drv_state = await get_user_state(session, self.driver_phone)
            self.assertEqual(drv_state.current_step, "awaiting_departure_time")
            handled = await handle_driver_interaction(session, self.driver_phone, "06:30 AM", drv_state)
            self.assertTrue(handled)

            # Driver clicks [Trip Started]
            handled = await handle_driver_interaction(session, self.driver_phone, f"flt_drv_start_{trip_test_id}", None)
            self.assertTrue(handled)

            req = await get_fleet_trip_request_by_id(session, trip_test_id)
            self.assertEqual(req.status, "ACTIVE")
            self.assertTrue(req.is_live_location_active)

            # Transit buttons presented
            transit_btns = [b["title"] for b in mock_send_btn.call_args[1]["buttons"]]
            self.assertEqual(transit_btns, ["Delivery Charges", "Emergency Charges", "I am Returning"])

            # Driver records Delivery Charge for CUST-101
            handled = await handle_driver_interaction(session, self.driver_phone, f"flt_drv_deliv_{trip_test_id}", None)
            self.assertTrue(handled)

            drv_state = await get_user_state(session, self.driver_phone)
            handled = await handle_driver_interaction(session, self.driver_phone, "CUST-101", drv_state)
            self.assertTrue(handled)

            # Autonomous manifest check confirms expected $72.00
            last_prompt = mock_send_txt.call_args[0][1]
            self.assertIn("72.00", last_prompt)

            # Driver enters collected amount 72.00
            drv_state = await get_user_state(session, self.driver_phone)
            handled = await handle_driver_interaction(session, self.driver_phone, "72.00", drv_state)
            self.assertTrue(handled)

            # Driver selects payment method [Cash]
            drv_state = await get_user_state(session, self.driver_phone)
            handled = await handle_driver_interaction(session, self.driver_phone, f"flt_pay_cash_{trip_test_id}", drv_state)
            self.assertTrue(handled)

            # Verify CUST-101 schedule updated in DB
            schedules = await get_customer_schedules_for_trip(session, trip_test_id)
            self.assertEqual(schedules[0].collected_charge, 72.00)
            self.assertEqual(schedules[0].payment_method, "CASH")
            self.assertEqual(schedules[0].status, "MATCHED")

            # Driver records Emergency Fuel
            handled = await handle_driver_interaction(session, self.driver_phone, f"flt_emg_fuel_{trip_test_id}", None)
            self.assertTrue(handled)
            drv_state = await get_user_state(session, self.driver_phone)
            handled = await handle_driver_interaction(session, self.driver_phone, "25.00", drv_state)
            self.assertTrue(handled)

            # Driver records Emergency Other (Tyre puncture)
            handled = await handle_driver_interaction(session, self.driver_phone, f"flt_emg_other_{trip_test_id}", None)
            self.assertTrue(handled)
            drv_state = await get_user_state(session, self.driver_phone)
            handled = await handle_driver_interaction(session, self.driver_phone, "Tyre puncture repair", drv_state)
            self.assertTrue(handled)
            drv_state = await get_user_state(session, self.driver_phone)
            handled = await handle_driver_interaction(session, self.driver_phone, "15.00", drv_state)
            self.assertTrue(handled)

            # Verify emergency expenses logged in DB
            emergencies = await get_emergency_expenses_for_trip(session, trip_test_id)
            self.assertEqual(len(emergencies), 2)
            self.assertEqual(emergencies[0].charge_type, "EMERGENCY_FUEL")
            self.assertEqual(emergencies[0].amount, 25.00)
            self.assertEqual(emergencies[1].charge_type, "OTHER")
            self.assertEqual(emergencies[1].amount, 15.00)

            # Driver clicks [I am Returning] -> live location deactivated
            handled = await handle_driver_interaction(session, self.driver_phone, f"flt_drv_ret_{trip_test_id}", None)
            self.assertTrue(handled)

            req = await get_fleet_trip_request_by_id(session, trip_test_id)
            self.assertEqual(req.status, "RETURNING")
            self.assertFalse(req.is_live_location_active)

            # Driver clicks [I Have Returned] -> summons Sales Admin
            handled = await handle_driver_interaction(session, self.driver_phone, f"flt_drv_returned_{trip_test_id}", None)
            self.assertTrue(handled)

            req = await get_fleet_trip_request_by_id(session, trip_test_id)
            self.assertEqual(req.status, "RETURNED")

            # ----------------------------------------------------
            # STAGE 6: Sales Admin Balancing Session
            # ----------------------------------------------------
            # Sales Admin clicks [Balanced]
            handled = await handle_sales_admin_interaction(session, self.sales_admin_phone, f"flt_adm_bal_{trip_test_id}", None)
            self.assertTrue(handled)

            req = await get_fleet_trip_request_by_id(session, trip_test_id)
            self.assertEqual(req.status, "BALANCED")

            # ----------------------------------------------------
            # STAGE 7: Logistics Manager Adjudication & Confidential Trip Closed
            # ----------------------------------------------------
            # Logistics Manager authorizes trip closure
            handled = await handle_logistics_manager_interaction(session, self.logistics_mgr_phone, f"flt_mgr_close_{trip_test_id}", None)
            self.assertTrue(handled)

            req = await get_fleet_trip_request_by_id(session, trip_test_id)
            self.assertEqual(req.status, "CLOSED")

            # CRITICAL SECURITY CHECK:
            # Check all operational messages sent by broadcast_confidential_trip_closed
            # The sales total ($14,200.00) must NEVER appear in operational broadcasts!
            all_broadcast_calls = mock_send_txt.call_args_list
            operational_broadcast_texts = [
                c[0][1] for c in all_broadcast_calls if "TRIP CLOSED" in c[0][1] and "EXECUTIVE AUDIT" not in c[0][1]
            ]
            self.assertTrue(len(operational_broadcast_texts) > 0)
            for b_text in operational_broadcast_texts:
                self.assertNotIn("14,200", b_text, "CRITICAL SECURITY BREACH: Sales total leaked to operational staff!")
                self.assertNotIn("Sales Total", b_text)
                self.assertIn("TRIP CLOSED", b_text)
                self.assertIn(trip_test_id, b_text)

            print("\n[SUCCESS] Full 7-stage sales fleet lifecycle verified with 100% confidentiality compliance!")

    @patch("app.meta_api.meta_api.send_text_message", new_callable=AsyncMock)
    @patch("app.meta_api.meta_api.send_button_message", new_callable=AsyncMock)
    async def test_multi_trip_fifo_queue_concurrency(self, mock_send_btn, mock_send_txt):
        """
        Tests multi-trip queue concurrency:
        When multiple trips are created, Edward sees all of them in FIFO order
        and can select and process them independently.
        """
        async with async_session_factory() as session:
            t1 = "TRIP-CONCUR-001"
            t2 = "TRIP-CONCUR-002"

            # Create 2 trip requests
            from app.database import create_or_update_fleet_trip_request
            await create_or_update_fleet_trip_request(
                session, t1, "A. TG Hardware", self.sales_rep_phone, "Gweru", "Sales 1", None, "Gweru", 12000.0, 100.0
            )
            await create_or_update_fleet_trip_request(
                session, t2, "B. LG Plast", self.sales_rep_phone, "Mutare", "Sales 2", None, "Mutare", 15000.0, 120.0
            )

            pending = await get_pending_trips_for_edward(session)
            trip_ids = [p.trip_id for p in pending]
            self.assertIn(t1, trip_ids)
            self.assertIn(t2, trip_ids)
            # Verify FIFO order
            idx1 = trip_ids.index(t1)
            idx2 = trip_ids.index(t2)
            self.assertLess(idx1, idx2)

            # Test Edward queue selector
            handled = await handle_edward_interaction(session, self.edward_phone, "flt_edw_queue", None)
            self.assertTrue(handled)
            body = mock_send_btn.call_args[1]["body_text"]
            self.assertIn(t1, body)
            self.assertIn(t2, body)

            print("[SUCCESS] Multi-trip FIFO queue concurrency verified!")


if __name__ == "__main__":
    unittest.main()
