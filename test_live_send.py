import asyncio
from app.meta_api import meta_api

async def test_send():
    phone = "919265368695"
    text = "👋 Hello Fazal! This is a test message from your IT Support Chatbot."
    print(f"Sending test message to {phone}...")
    res = await meta_api.send_text_message(phone, text)
    print("Meta API Response:", res)

if __name__ == "__main__":
    asyncio.run(test_send())
