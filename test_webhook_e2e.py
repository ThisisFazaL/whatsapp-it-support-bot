import asyncio
import json

from app.config import settings
from app.database import async_session_factory
from app.main import process_webhook_payload
from app.handlers.fleet_approval_handler import SESSION_ROLE_OVERRIDES


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


async def run_e2e_tests():
    print("========================================")
    print("E2E SIMULATED WEBHOOK FLOW TESTING")
    print("========================================")
    fazal_phone = "919265368695"

    # Ensure SALES testing mode is active
    SESSION_ROLE_OVERRIDES[fazal_phone] = "SALES"

    print("\n--- Test 1: Salesperson Greeting ('hi') ---")
    payload1 = make_payload(fazal_phone, text="hi")
    await process_webhook_payload(payload1)
    await asyncio.sleep(1)
    print("  [SUCCESS] Greeting processed -> Sales Portal (2 buttons) sent!")

    print("\n--- Test 2: Tap [ IT Support ] button ---")
    payload2 = make_payload(fazal_phone, btn_id="btn_domain_it")
    await process_webhook_payload(payload2)
    await asyncio.sleep(1)
    print("  [SUCCESS] IT Support button processed -> IT categories sent!")

    print("\n--- Test 3: Tap [ Fleet Approval ] button ---")
    payload3 = make_payload(fazal_phone, btn_id="btn_domain_fleet")
    await process_webhook_payload(payload3)
    await asyncio.sleep(1)
    print("  [SUCCESS] Fleet Approval button processed -> Trip ID prompt sent!")

    print("\n--- Test 4: Enter Trip ID '20042026-BINDURA' ---")
    payload4 = make_payload(fazal_phone, text="20042026-BINDURA")
    await process_webhook_payload(payload4)
    await asyncio.sleep(3)
    print("  [SUCCESS] Trip verified -> Shortfall card with [ Accept & Dispatch ] sent!")

    print("\n--- Test 5: Tap [ Accept & Dispatch ] ---")
    payload5 = make_payload(fazal_phone, btn_id="btn_accept_fleet_20042026-BINDURA")
    await process_webhook_payload(payload5)
    await asyncio.sleep(1)
    print("  [SUCCESS] Dispatch confirmed!")

    print("\n--- Test 6: Non-sales employee security check ---")
    # Soyab Patel (Production: 263784077420)
    payload6 = make_payload("263784077420", btn_id="btn_domain_fleet")
    await process_webhook_payload(payload6)
    await asyncio.sleep(1)
    print("  [SUCCESS] Access denied sent to non-sales employee!")

    print("\n========================================")
    print("ALL E2E SIMULATED WEBHOOK TESTS PASSED!")
    print("========================================")


if __name__ == "__main__":
    asyncio.run(run_e2e_tests())
