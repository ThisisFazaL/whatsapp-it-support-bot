import logging
import httpx
from app.config import settings

logger = logging.getLogger("meta_api")
logging.basicConfig(level=logging.INFO)

class MetaWhatsAppAPI:
    def __init__(self):
        self.phone_number_id = settings.phone_number_id
        self.access_token = settings.meta_access_token
        self.version = settings.meta_graph_version
        self.base_url = f"https://graph.facebook.com/{self.version}/{self.phone_number_id}/messages"

    async def send_text_message(self, to_phone: str, text: str) -> dict:
        """
        Sends a WhatsApp text message to the specified recipient phone number via Meta Graph API.
        """
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        # Clean phone number (strip spaces, +, leading zeroes if needed)
        clean_phone = to_phone.replace("+", "").replace(" ", "").strip()

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": clean_phone,
            "type": "text",
            "text": {
                "body": text
            }
        }

        logger.info(f"[OUTGOING WHATSAPP -> {clean_phone}]\n{text}\n----------------------------------")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self.base_url, headers=headers, json=payload)
                response_json = response.json()
                if response.status_code != 200:
                    logger.error(f"Meta Graph API Error ({response.status_code}): {response_json}")
                else:
                    logger.info(f"Meta Graph API Success: {response_json}")
                return response_json
        except Exception as e:
            logger.error(f"Failed to communicate with Meta WhatsApp API: {e}")
            return {"error": str(e)}

    async def send_button_message(self, to_phone: str, body_text: str, buttons: list, header_text: str = None, footer_text: str = None) -> dict:
        """
        Sends interactive quick reply buttons to a WhatsApp recipient via Meta Graph API.
        `buttons` is a list of dicts: [{"id": "claim_TKT-...", "title": "⚡ Accept Ticket"}]
        """
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        clean_phone = to_phone.replace("+", "").replace(" ", "").strip()

        interactive_dict = {
            "type": "button",
            "body": {"text": body_text},
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": b["id"][:256],
                            "title": b["title"][:20]  # Meta API max title length is 20 chars
                        }
                    } for b in buttons
                ]
            }
        }
        if header_text:
            interactive_dict["header"] = {"type": "text", "text": header_text[:60]}
        if footer_text:
            interactive_dict["footer"] = {"text": footer_text[:60]}

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": clean_phone,
            "type": "interactive",
            "interactive": interactive_dict
        }

        logger.info(f"[OUTGOING INTERACTIVE BUTTONS -> {clean_phone}]\n{header_text}\n{body_text}")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self.base_url, headers=headers, json=payload)
                response_json = response.json()
                if response.status_code != 200:
                    logger.error(f"Meta Graph API Button Error ({response.status_code}): {response_json}")
                    # Fallback to text message if interactive button fails
                    fallback_msg = f"{header_text or ''}\n\n{body_text}\n\n{footer_text or ''}".strip()
                    return await self.send_text_message(clean_phone, fallback_msg)
                else:
                    logger.info(f"Meta Graph API Button Success: {response_json}")
                return response_json
        except Exception as e:
            logger.error(f"Failed to send button message via Meta API: {e}")
            fallback_msg = f"{header_text or ''}\n\n{body_text}\n\n{footer_text or ''}".strip()
            return await self.send_text_message(clean_phone, fallback_msg)

    async def send_document_message(self, to_phone: str, document_url: str, filename: str, caption: str = "") -> dict:
        """
        Sends a PDF or Document file to WhatsApp recipient via Meta Graph API.
        """
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        clean_phone = to_phone.replace("+", "").replace(" ", "").strip()

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": clean_phone,
            "type": "document",
            "document": {
                "link": document_url,
                "filename": filename,
                "caption": caption
            }
        }

        logger.info(f"[OUTGOING DOCUMENT -> {clean_phone}]\nFile: {filename}\nURL: {document_url}")

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(self.base_url, headers=headers, json=payload)
                response_json = response.json()
                if response.status_code != 200:
                    logger.error(f"Meta Graph API Document Error ({response.status_code}): {response_json}")
                else:
                    logger.info(f"Meta Graph API Document Success: {response_json}")
                return response_json
        except Exception as e:
            logger.error(f"Failed to send document message via Meta API: {e}")
            return {"error": str(e)}

    async def send_template_message(self, to_phone: str, template_name: str, lang_code: str = "en") -> dict:
        """
        Sends an approved Meta WhatsApp Template message to the recipient phone number.
        """
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        clean_phone = to_phone.replace("+", "").replace(" ", "").strip()

        payload = {
            "messaging_product": "whatsapp",
            "to": clean_phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {
                    "code": lang_code
                }
            }
        }

        logger.info(f"[OUTGOING TEMPLATE '{template_name}' -> {clean_phone}]")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self.base_url, headers=headers, json=payload)
                response_json = response.json()
                if response.status_code != 200:
                    logger.error(f"Meta Graph API Template Error ({response.status_code}): {response_json}")
                else:
                    logger.info(f"Meta Graph API Template Success: {response_json}")
                return response_json
        except Exception as e:
            logger.error(f"Failed to send template message via Meta API: {e}")
            return {"error": str(e)}

meta_api = MetaWhatsAppAPI()
