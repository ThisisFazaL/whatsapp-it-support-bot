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
    FleetTripRequest, FleetCustomerSchedule, FleetEmergencyExpense,
    FleetTripApproval, FleetPendingLedger,
    get_fleet_trip_request_by_id, get_customer_schedules_for_trip,
    create_or_update_fleet_trip_request, save_customer_schedules_batch
)
from app.workshop.models import WorkshopStaff
from app.state_manager import get_user_state, set_user_state, clear_user_state
from app.handlers.fleet_approval_handler import finalize_stage2_dispatch
from app.handlers.driver_handler import (
    send_driver_transit_menu,
    send_driver_returning_menu,
    return_to_appropriate_driver_menu,
    handle_driver_interaction
)
from app.handlers.sales_admin_handler import notify_sales_admin_balancing_session


class TestRefinementsAndEdgeCases(unittest.IsolatedAsyncioTestCase):
    _db_initialized = False

    async def asyncSetUp(self):
        if not TestRefinementsAndEdgeCases._db_initialized:
            await init_db_models()
            TestRefinementsAndEdgeCases._db_initialized = True

        self.driver_phone = "263788112771"
        self.sales_rep_phone = "263772111222"
        self.trip_id = "23092026-NORTON"

        async with async_session_factory() as session:
            for model in [FleetEmergencyExpense, FleetCustomerSchedule, FleetTripRequest, FleetTripApproval, FleetPendingLedger]:
                await session.execute(delete(model))
            await session.commit()

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

    async def test_multi_customer_dispatch_creates_individual_schedules(self):
        """Test that multiple customers from Favlogix create distinct FleetCustomerSchedule rows with real names."""
        customers_data = [
            {
                "customer_name": "Demo Building Contractor",
                "customer_id": "ORD-101",
                "order_id": "ORD-101",
                "order_total": 2155.69,
                "to_collect": 0.0
            },
            {
                "customer_name": "Demo Hatfield Water Services",
                "customer_id": "ORD-102",
                "order_id": "ORD-102",
                "order_total": 294.99,
                "to_collect": 0.0
            }
        ]

        async with async_session_factory() as session:
            with patch("app.meta_api.meta_api.send_text_message", new_callable=AsyncMock) as mock_text, \
                 patch("app.meta_api.meta_api.send_button_message", new_callable=AsyncMock), \
                 patch("app.handlers.logistics_handler.notify_edward_new_trip", new_callable=AsyncMock):

                await finalize_stage2_dispatch(
                    session=session,
                    phone=self.sales_rep_phone,
                    employee=None,
                    data={
                        "trip_id": self.trip_id,
                        "company_name": "A. TG Hardware",
                        "dest": "Norton",
                        "route": "Norton",
                        "sales_val": 2450.68,
                        "transport_charge": 0.0,
                        "customers": customers_data
                    }
                )

            schedules = await get_customer_schedules_for_trip(session, self.trip_id)
            self.assertEqual(len(schedules), 2)
            names = [s.reference_note for s in schedules]
            self.assertIn("Demo Building Contractor", names)
            self.assertIn("Demo Hatfield Water Services", names)
            self.assertNotIn("GENERAL", [s.customer_id for s in schedules])

    async def test_delivery_charges_omitted_when_transport_charge_is_zero(self):
        """Test that when transport charge is 0, driver transit menu omits [Delivery Charges]."""
        async with async_session_factory() as session:
            await create_or_update_fleet_trip_request(
                session=session,
                trip_id=self.trip_id,
                company_name="A. TG Hardware",
                salesperson_phone=self.sales_rep_phone,
                destination_city="Norton",
                transport_charge=0.0
            )

            # Schedule with 0 expected charge
            await save_customer_schedules_batch(
                session=session,
                trip_id=self.trip_id,
                schedules=[
                    {"customer_id": "ORD-101", "reference_note": "Demo Building Contractor", "expected_charge": 0.0},
                    {"customer_id": "ORD-102", "reference_note": "Demo Hatfield Water Services", "expected_charge": 0.0}
                ]
            )

            with patch("app.meta_api.meta_api.send_button_message", new_callable=AsyncMock) as mock_btn:
                await send_driver_transit_menu(session, self.driver_phone, self.trip_id)
                self.assertTrue(mock_btn.called)
                sent_buttons = mock_btn.call_args[1]["buttons"]
                button_ids = [b["id"] for b in sent_buttons]
                button_titles = [b["title"] for b in sent_buttons]

                # Delivery Charges MUST NOT be present
                self.assertNotIn("Delivery Charges", button_titles)
                self.assertFalse(any("flt_drv_deliv_" in bid for bid in button_ids))
                # Only Emergency Charges and I Have Returned
                self.assertEqual(len(sent_buttons), 2)
                self.assertIn("Emergency Charges", button_titles)
                self.assertIn("I Have Returned", button_titles)

    async def test_delivery_charges_removed_permanently_from_transit_menu(self):
        """Test that delivery charges button is removed from driver transit menu even when transport charge > 0."""
        async with async_session_factory() as session:
            await create_or_update_fleet_trip_request(
                session=session,
                trip_id=self.trip_id,
                company_name="A. TG Hardware",
                salesperson_phone=self.sales_rep_phone,
                destination_city="Norton",
                transport_charge=50.0
            )
            await save_customer_schedules_batch(
                session=session,
                trip_id=self.trip_id,
                schedules=[
                    {"customer_id": "ORD-101", "reference_note": "Demo Customer", "expected_charge": 50.0}
                ]
            )

            with patch("app.meta_api.meta_api.send_button_message", new_callable=AsyncMock) as mock_btn:
                await send_driver_transit_menu(session, self.driver_phone, self.trip_id)
                self.assertTrue(mock_btn.called)
                sent_buttons = mock_btn.call_args[1]["buttons"]
                button_titles = [b["title"] for b in sent_buttons]
                self.assertNotIn("Delivery Charges", button_titles)
                self.assertIn("I Have Returned", button_titles)
                self.assertIn("Emergency Charges", button_titles)
                self.assertEqual(len(sent_buttons), 2)

    async def test_emergency_fuel_prompt_and_video_instruction(self):
        """Test emergency fuel prompts driver not to send video to WhatsApp and to keep it for balancing."""
        async with async_session_factory() as session:
            trip = await create_or_update_fleet_trip_request(
                session=session,
                trip_id=self.trip_id,
                company_name="A. TG Hardware",
                salesperson_phone=self.sales_rep_phone,
                destination_city="Norton"
            )
            trip.driver_phone = self.driver_phone
            trip.driver_name = "Terrence Mupfumi"
            trip.status = "ACTIVE"
            await session.commit()

            with patch("app.meta_api.meta_api.send_text_message", new_callable=AsyncMock) as mock_text:
                await handle_driver_interaction(
                    session=session,
                    phone=self.driver_phone,
                    message_text=f"flt_emg_fuel_{self.trip_id}",
                    state=None
                )
                self.assertTrue(mock_text.called)
                prompt_text = mock_text.call_args[0][1]
                self.assertIn("Do NOT send this video to WhatsApp", prompt_text)
                self.assertIn("fuel pump meter", prompt_text)
                self.assertIn("fuel gauge", prompt_text)
                self.assertIn("date and time", prompt_text)

            # Test that sending 'video' in awaiting_fuel_amount reminds driver not to send it to bot
            st = await get_user_state(session, self.driver_phone)
            self.assertEqual(st.current_step, "awaiting_fuel_amount")

            with patch("app.meta_api.meta_api.send_text_message", new_callable=AsyncMock) as mock_text:
                await handle_driver_interaction(
                    session=session,
                    phone=self.driver_phone,
                    message_text="Here is my fuel video",
                    state=st
                )
                self.assertTrue(mock_text.called)
                reply = mock_text.call_args[0][1]
                self.assertIn("Please do NOT send the video here", reply)
                self.assertIn("physical balancing", reply)

    async def test_returning_driver_state_preserved_after_emergency_fuel(self):
        """Test that after driver clicks 'I am Returning', entering emergency fuel returns to [I Have Returned]."""
        async with async_session_factory() as session:
            trip = await create_or_update_fleet_trip_request(
                session=session,
                trip_id=self.trip_id,
                company_name="A. TG Hardware",
                salesperson_phone=self.sales_rep_phone,
                destination_city="Norton"
            )
            trip.driver_phone = self.driver_phone
            trip.driver_name = "Terrence Mupfumi"
            trip.status = "ACTIVE"
            await session.commit()

            # 1. Driver clicks [I Have Returned]
            with patch("app.meta_api.meta_api.send_text_message", new_callable=AsyncMock) as mock_txt:
                await handle_driver_interaction(
                    session=session,
                    phone=self.driver_phone,
                    message_text=f"flt_drv_returned_{self.trip_id}",
                    state=None
                )
                self.assertTrue(mock_txt.called)
                prompt = mock_txt.call_args[0][1]
                self.assertIn("Return Odometer", prompt)

            # Trip should now be in RETURNING status
            t_updated = await get_fleet_trip_request_by_id(session, self.trip_id)
            self.assertEqual(t_updated.status, "RETURNING")
            self.assertIsNotNone(t_updated.returning_at)

            # 2. Driver clicks [Emergency Fuel]
            with patch("app.meta_api.meta_api.send_text_message", new_callable=AsyncMock):
                await handle_driver_interaction(
                    session=session,
                    phone=self.driver_phone,
                    message_text=f"flt_emg_fuel_{self.trip_id}",
                    state=None
                )
            st = await get_user_state(session, self.driver_phone)
            self.assertEqual(st.current_step, "awaiting_fuel_amount")

            # 3. Driver enters fuel amount $30.00
            with patch("app.meta_api.meta_api.send_button_message", new_callable=AsyncMock) as mock_btn, \
                 patch("app.meta_api.meta_api.send_text_message", new_callable=AsyncMock):
                await handle_driver_interaction(
                    session=session,
                    phone=self.driver_phone,
                    message_text="30.00",
                    state=st
                )

                # The menu returned MUST be RETURNING menu (showing "I Have Returned"), NOT transit menu ("I am Returning")
                self.assertTrue(mock_btn.called)
                driver_menu_buttons = None
                for call in mock_btn.call_args_list:
                    if call[1].get("header_text") == "RETURNING TO BASE" or "RETURNING TO BASE" in call[1].get("body_text", ""):
                        driver_menu_buttons = call[1].get("buttons")

                self.assertIsNotNone(driver_menu_buttons, "Expected 'RETURNING TO BASE' menu to be sent to driver!")
                titles = [b["title"] for b in driver_menu_buttons]
                self.assertIn("I Have Returned", titles)
                self.assertNotIn("I am Returning", titles)

            # 4. If driver sends "cancel" while returning, they should also return to [I Have Returned]
            st = await get_user_state(session, self.driver_phone)
            with patch("app.meta_api.meta_api.send_button_message", new_callable=AsyncMock) as mock_btn:
                await handle_driver_interaction(
                    session=session,
                    phone=self.driver_phone,
                    message_text="cancel",
                    state=st
                )
                titles = [b["title"] for b in mock_btn.call_args[1]["buttons"]]
                self.assertIn("I Have Returned", titles)
                self.assertNotIn("I am Returning", titles)

    async def test_sales_admin_balancing_shows_video_note_and_customer_names(self):
        """Test sales admin balancing card mentions driver's video verification note when fuel expense exists."""
        async with async_session_factory() as session:
            trip = await create_or_update_fleet_trip_request(
                session=session,
                trip_id=self.trip_id,
                company_name="A. TG Hardware",
                salesperson_phone=self.sales_rep_phone,
                destination_city="Norton"
            )
            trip.driver_phone = self.driver_phone
            trip.driver_name = "Terrence Mupfumi"
            trip.truck_plate = "AGY-101"
            trip.status = "RETURNED"
            await session.commit()
            await save_customer_schedules_batch(
                session=session,
                trip_id=self.trip_id,
                schedules=[
                    {"customer_id": "ORD-101", "reference_note": "Demo Building Contractor", "expected_charge": 0.0},
                    {"customer_id": "ORD-102", "reference_note": "Demo Hatfield Water Services", "expected_charge": 0.0}
                ]
            )

            # Add emergency fuel expense
            exp = FleetEmergencyExpense(
                trip_id=self.trip_id,
                driver_phone=self.driver_phone,
                charge_type="EMERGENCY_FUEL",
                amount=35.0,
                description="Emergency Diesel refuel",
                has_video_evidence=True,
                status="APPROVED"
            )
            session.add(exp)
            await session.commit()

            with patch("app.meta_api.meta_api.send_button_message", new_callable=AsyncMock) as mock_btn:
                await notify_sales_admin_balancing_session(session, self.trip_id)
                self.assertTrue(mock_btn.called)
                card_body = mock_btn.call_args[1]["body_text"]

                # Verify customer names are rendered
                self.assertIn("Demo Building Contractor", card_body)
                self.assertIn("Demo Hatfield Water Services", card_body)
                # Verify video note
                self.assertIn("Driver to present recorded video of fuel pump & fuel gauge on phone", card_body)

    async def test_operational_closing_broadcast_excludes_financials(self):
        """Test that operational closing message for all excludes transport, emergencies, and allowances."""
        from app.handlers.logistics_manager_handler import broadcast_confidential_trip_closed
        async with async_session_factory() as session:
            trip = await create_or_update_fleet_trip_request(
                session=session,
                trip_id=self.trip_id,
                company_name="A. TG Hardware",
                salesperson_phone=self.sales_rep_phone,
                destination_city="Norton",
                transport_charge=80.0
            )
            trip.driver_phone = self.driver_phone
            trip.driver_name = "Terrence Mupfumi"
            trip.truck_plate = "AGY-101"
            trip.status = "BALANCED"
            trip.reimbursement_status = "NONE"
            await session.commit()

            # Add emergency expense and schedule
            exp = FleetEmergencyExpense(
                trip_id=self.trip_id,
                driver_phone=self.driver_phone,
                charge_type="EMERGENCY_FUEL",
                amount=45.0,
                description="Diesel",
                has_video_evidence=True,
                status="APPROVED"
            )
            session.add(exp)
            await session.commit()

            with patch("app.meta_api.meta_api.send_text_message", new_callable=AsyncMock) as mock_txt:
                await broadcast_confidential_trip_closed(session, self.trip_id)
                self.assertTrue(mock_txt.called)

                # Find the operational message sent to operational staff / tester
                operational_msgs = [
                    call[0][1] for call in mock_txt.call_args_list
                    if "TRIP CLOSED" in call[0][1] and "EXECUTIVE AUDIT" not in call[0][1]
                ]
                self.assertTrue(len(operational_msgs) > 0)
                for op_msg in operational_msgs:
                    # Must contain basic identifiers
                    self.assertIn("TRIP CLOSED", op_msg)
                    self.assertIn(self.trip_id, op_msg)
                    self.assertIn("Terrence Mupfumi", op_msg)
                    self.assertIn("AGY-101", op_msg)
                    self.assertIn("Balancing Status", op_msg)

                    # MUST NOT contain financial figures
                    self.assertNotIn("Transport Collected", op_msg)
                    self.assertNotIn("Emergency Expenses", op_msg)
                    self.assertNotIn("Allowance Reconciled", op_msg)
                    self.assertNotIn("Cash:", op_msg)
                    self.assertNotIn("Bank:", op_msg)


if __name__ == "__main__":
    unittest.main()
