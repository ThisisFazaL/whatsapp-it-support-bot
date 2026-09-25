import asyncio
from unittest.mock import AsyncMock, patch
from sqlalchemy import select

from app.database import async_session_factory, Employee, SupportAdmin, Category, Location, ConversationState
from app.workshop.models import WorkshopStaff
from app.main import process_webhook_payload
from app.state_manager import get_user_state, clear_user_state

def make_payload(phone: str, text: str = "", btn_id: str = ""):
    msg_id = f"wamid_test_{asyncio.get_event_loop().time()}"
    msg_obj = {
        "from": phone,
        "id": msg_id,
        "timestamp": "1726738000"
    }
    if btn_id:
        msg_obj["type"] = "interactive"
        msg_obj["interactive"] = {
            "type": "button_reply",
            "button_reply": {"id": btn_id, "title": btn_id}
        }
    else:
        msg_obj["type"] = "text"
        msg_obj["text"] = {"body": text}

    return {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [msg_obj]
                }
            }]
        }]
    }

async def run_all_role_tests():
    print("================================================================")
    print("STARTING COMPREHENSIVE ROLE & FARUK PATEL E2E AUDIT")
    print("================================================================")

    with patch("app.meta_api.meta_api.send_button_message", new_callable=AsyncMock) as mock_btn, \
         patch("app.meta_api.meta_api.send_text_message", new_callable=AsyncMock) as mock_txt, \
         patch("app.meta_api.meta_api.send_image_message", new_callable=AsyncMock) as mock_img:

        faruk_phone = "263780515663"

        async with async_session_factory() as session:
            # Verify Faruk Patel in DB
            faruk_emp = (await session.execute(select(Employee).where(Employee.phone == faruk_phone))).scalars().first()
            print(f"\n[INFO] Faruk Patel in DB: {faruk_emp.full_name if faruk_emp else 'None'}, is_maintenance_reporter={faruk_emp.is_maintenance_reporter if faruk_emp else False}")
            assert faruk_emp is not None, "Faruk Patel not found in DB!"
            assert faruk_emp.is_maintenance_reporter is True, "Faruk Patel must be maintenance reporter!"

        # -----------------------------------------------------------------
        # TEST 1: Faruk Patel Ticket Flow (IT Support domain)
        # -----------------------------------------------------------------
        print("\n--- TEST 1: Faruk Patel sends 'hi' ---")
        async with async_session_factory() as session:
            await clear_user_state(session, faruk_phone)
        
        await process_webhook_payload(make_payload(faruk_phone, text="hi"))
        
        async with async_session_factory() as session:
            state = await get_user_state(session, faruk_phone)
            print(f"  State after 'hi': step={state.current_step if state else None}, flow={state.flow_name if state else None}")
            assert state is not None, "Expected state to exist"
            assert state.current_step == "select_domain", f"Expected select_domain, got {state.current_step}"

        print("\n--- TEST 1.2: Faruk Patel taps [ IT Support ] (btn_domain_it) ---")
        await process_webhook_payload(make_payload(faruk_phone, btn_id="btn_domain_it"))

        async with async_session_factory() as session:
            state = await get_user_state(session, faruk_phone)
            print(f"  State after tapping IT Support: step={state.current_step if state else None}, data={state.current_data if state else None}")
            assert state is not None, "Expected state to exist"
            assert state.current_step == "awaiting_category", f"CRITICAL FAILURE! Faruk looped! Expected awaiting_category, got {state.current_step}"
            assert state.current_data.get("domain") == "IT", f"Expected domain == IT, got {state.current_data.get('domain')}"
            print("  >>> SUCCESS: Faruk Patel successfully advanced to IT Categories Menu (NO LOOP)!")

        print("\n--- TEST 1.3: Faruk Patel selects Category 1 (Hardware) ---")
        await process_webhook_payload(make_payload(faruk_phone, text="1"))

        async with async_session_factory() as session:
            state = await get_user_state(session, faruk_phone)
            print(f"  State after choosing category 1: step={state.current_step if state else None}")
            assert state is not None, "Expected state to exist"
            assert state.current_step == "awaiting_subcategory", f"Expected awaiting_subcategory, got {state.current_step}"
            print("  >>> SUCCESS: Faruk Patel subcategory menu reached!")

        # -----------------------------------------------------------------
        # TEST 2: Faruk Patel Ticket Flow (Projects domain)
        # -----------------------------------------------------------------
        print("\n--- TEST 2: Faruk Patel starts over and taps [ Projects ] ---")
        async with async_session_factory() as session:
            await clear_user_state(session, faruk_phone)
        
        await process_webhook_payload(make_payload(faruk_phone, text="hi"))
        await process_webhook_payload(make_payload(faruk_phone, btn_id="btn_domain_maint"))

        async with async_session_factory() as session:
            state = await get_user_state(session, faruk_phone)
            print(f"  State after tapping Projects: step={state.current_step if state else None}, domain={state.current_data.get('domain') if state else None}")
            assert state is not None, "Expected state to exist"
            assert state.current_step == "select_location", f"Expected select_location, got {state.current_step}"
            assert state.current_data.get("domain") == "MAINTENANCE", f"Expected domain == MAINTENANCE, got {state.current_data.get('domain')}"
            print("  >>> SUCCESS: Faruk Patel project location selection reached!")

        # -----------------------------------------------------------------
        # TEST 3: Standard IT Employee (Single role)
        # -----------------------------------------------------------------
        std_emp_phone = "263783041705" # David Nyandare (Shop Manager, IT single domain)
        print(f"\n--- TEST 3: Standard IT Employee ({std_emp_phone}) sends 'hi' ---")
        async with async_session_factory() as session:
            await clear_user_state(session, std_emp_phone)

        await process_webhook_payload(make_payload(std_emp_phone, text="hi"))

        async with async_session_factory() as session:
            state = await get_user_state(session, std_emp_phone)
            print(f"  State for standard employee: step={state.current_step if state else None}")
            assert state is not None, "Expected state to exist"
            assert state.current_step == "awaiting_category", f"Expected awaiting_category directly, got {state.current_step}"
            print("  >>> SUCCESS: Standard IT employee gets categories directly with 0 friction!")

        # -----------------------------------------------------------------
        # TEST 4: Dual-Domain Staff (Edward Chemhere: Supervisor + Employee)
        # -----------------------------------------------------------------
        edward_phone = "263715025982"
        print(f"\n--- TEST 4: Dual-domain staff Edward ({edward_phone}) taps [ IT Support ] from portal ---")
        async with async_session_factory() as session:
            await clear_user_state(session, edward_phone)

        # Tap portal IT button
        await process_webhook_payload(make_payload(edward_phone, btn_id="btn_portal_it"))

        async with async_session_factory() as session:
            state = await get_user_state(session, edward_phone)
            print(f"  State after tapping btn_portal_it: step={state.current_step if state else None}")
            assert state is not None, "Expected state to exist"
            assert state.current_step == "awaiting_category", f"Expected awaiting_category, got {state.current_step}"
            print("  >>> SUCCESS: Dual domain staff switched to IT Support categories seamlessly!")

        # -----------------------------------------------------------------
        # TEST 5: IT Admin (Omar Arizai / Faisal Kassim)
        # -----------------------------------------------------------------
        faisal_phone = "263780100503"
        print(f"\n--- TEST 5: IT Admin Faisal ({faisal_phone}) taps [ IT Support ] from portal ---")
        async with async_session_factory() as session:
            await clear_user_state(session, faisal_phone)

        mock_btn.reset_mock()
        await process_webhook_payload(make_payload(faisal_phone, btn_id="btn_portal_it"))
        print(f"  Admin dashboard call triggered: {mock_btn.called}")
        assert mock_btn.called, "Expected admin dashboard buttons to be sent to admin!"
        print("  >>> SUCCESS: IT Admin portal switch presents Admin Dashboard properly!")

        print("\n================================================================")
        print("ALL 5 END-TO-END ROLE & WORKFLOW TESTS PASSED PERFECTLY!")
        print("================================================================")

if __name__ == "__main__":
    asyncio.run(run_all_role_tests())
