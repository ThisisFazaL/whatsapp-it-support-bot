import asyncio
import httpx
from app.config import settings

async def subscribe_waba():
    waba_id = "1070310408677348" # From payload screenshot
    url = f"https://graph.facebook.com/{settings.meta_graph_version}/{waba_id}/subscribed_apps"
    headers = {
        "Authorization": f"Bearer {settings.meta_access_token}"
    }
    
    print(f"Subscribing App to WhatsApp Business Account ({waba_id})...")
    async with httpx.AsyncClient(timeout=10.0) as client:
        res = await client.post(url, headers=headers)
        print("Meta Graph API Response Status:", res.status_code)
        print("Meta Graph API Response Body:", res.json())

if __name__ == "__main__":
    asyncio.run(subscribe_waba())
