import asyncio
import time
from httpx import AsyncClient, ASGITransport
from app.main import app

async def run_simulation():
    print("=" * 65)
    print("WHATSAPP IT SUPPORT CHATBOT - AUTOMATED TEST SUITE")
    print("=" * 65)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Health Check
        resp = await client.get("/health")
        print(f"Health Check: {resp.json()}")

        w_counter = int(time.time())

        def build_payload(phone: str, text: str):
            nonlocal w_counter
            w_counter += 1
            return {
                "object": "whatsapp_business_account",
                "entry": [{
                    "id": "1070310408677348",
                    "changes": [{
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15556729057",
                                "phone_number_id": "1145527058653682"
                            },
                            "contacts": [{"profile": {"name": "Test User"}, "wa_id": phone}],
                            "messages": [{
                                "from": phone,
                                "id": f"wamid.TEST_{w_counter}",
                                "timestamp": str(int(time.time())),
                                "text": {"body": text},
                                "type": "text"
                            }]
                        },
                        "field": "messages"
                    }]
                }]
            }

        # TEST 1: Unregistered User
        print("\n--- TEST 1: Unregistered User Attempt ---")
        p = build_payload("999999999999", "Hi")
        res = await client.post("/webhook/meta-whatsapp", json=p)
        print(f"[USER (999999999999)]: 'Hi'")
        print(f"[BOT RESPONSE CODE]: {res.status_code} | {res.json()}")

        # TEST 2: Registered Employee Creates Ticket
        emp_phone = "919265368695"
        print(f"\n--- TEST 2: Registered Employee Ticket Creation Flow ---")
        
        steps = [
            ("Hi", "Start flow"),
            ("1", "Select Category 1"),
            ("1", "Select Subcategory 1"),
            ("1", "Select Issue 1"),
            ("Laptop screen flickers when HDMI cable connected.", "Provide description"),
            ("skip", "Skip photo attachment"),
            ("3", "Select Priority 3 (High)")
        ]

        for text, desc in steps:
            p = build_payload(emp_phone, text)
            res = await client.post("/webhook/meta-whatsapp", json=p)
            print(f"[USER ({emp_phone})]: '{text}' ({desc}) -> {res.json()}")

        # Check Recent Tickets
        t_res = await client.get("/tickets")
        tickets = t_res.json().get("tickets", [])
        latest = tickets[0] if tickets else None
        if latest:
            print(f"\n[CREATED TICKET]: {latest['ticket_number']} | Status: {latest['status']} | Employee: {latest['employee']}")

        # TEST 3: Admin Resolves Ticket
        if latest:
            t_num = latest["ticket_number"]
            admin_phone = "919265368695" # Fazal is admin
            print(f"\n--- TEST 3: Admin Resolves Ticket ({t_num}) ---")
            p = build_payload(admin_phone, f"resolve {t_num}")
            res = await client.post("/webhook/meta-whatsapp", json=p)
            print(f"[ADMIN ({admin_phone})]: 'resolve {t_num}' -> {res.json()}")

            # TEST 4: Employee Confirms Resolution (1 = Close)
            print(f"\n--- TEST 4: Employee Confirms Resolution (1 = Close Ticket) ---")
            p = build_payload(emp_phone, "1")
            res = await client.post("/webhook/meta-whatsapp", json=p)
            print(f"[EMPLOYEE ({emp_phone})]: '1' -> {res.json()}")

            t_res = await client.get("/tickets")
            updated_tickets = t_res.json().get("tickets", [])
            up_latest = next((t for t in updated_tickets if t["ticket_number"] == t_num), None)
            if up_latest:
                print(f"\n[FINAL TICKET STATUS]: {up_latest['ticket_number']} -> Status: {up_latest['status']}")

if __name__ == "__main__":
    asyncio.run(run_simulation())
