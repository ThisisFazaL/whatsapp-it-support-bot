import asyncio
import httpx

async def test_payload():
    url = "https://uninjured-seducing-cycle.ngrok-free.dev/webhook/meta-whatsapp"
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "1070310408677348",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15556729057",
                                "phone_number_id": "1145527058653682"
                            },
                            "contacts": [
                                {
                                    "profile": {
                                        "name": "Fazal Saiyed"
                                    },
                                    "wa_id": "919265368695"
                                }
                            ],
                            "messages": [
                                {
                                    "from": "919265368695",
                                    "id": "wamid.TEST12346",
                                    "timestamp": "1786526610",
                                    "type": "text",
                                    "text": {
                                        "body": "1"
                                    }
                                }
                            ]
                        },
                        "field": "messages"
                    }
                ]
            }
        ]
    }
    
    print(f"Sending '1' payload to {url}...")
    async with httpx.AsyncClient(timeout=10.0) as client:
        res = await client.post(url, json=payload)
        print("Server Response Status:", res.status_code)
        print("Server Response Body:", res.json())

if __name__ == "__main__":
    asyncio.run(test_payload())
