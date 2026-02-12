"""WhatsApp Business Cloud API adapter."""

import hashlib
import hmac
import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


class WhatsAppAdapter:
    """Client for WhatsApp Business Cloud API (Meta Graph API v21.0)."""

    BASE_URL = "https://graph.facebook.com/v21.0"

    def __init__(self):
        self.phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
        self.access_token = settings.WHATSAPP_ACCESS_TOKEN

    @property
    def messages_url(self):
        return f"{self.BASE_URL}/{self.phone_number_id}/messages"

    @property
    def headers(self):
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def send_text_message(self, to_phone: str, body: str) -> dict:
        """Send a plain text message."""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone.replace("+", ""),
            "type": "text",
            "text": {"body": body},
        }
        return self._send(payload)

    def send_template_message(self, to_phone: str, template_name: str, params: dict | None = None) -> dict:
        """Send a template message (required for initiating conversations)."""
        template = {"name": template_name, "language": {"code": "en_US"}}
        if params:
            components = []
            if params.get("body_params"):
                components.append(
                    {
                        "type": "body",
                        "parameters": [{"type": "text", "text": p} for p in params["body_params"]],
                    }
                )
            template["components"] = components

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone.replace("+", ""),
            "type": "template",
            "template": template,
        }
        return self._send(payload)

    def send_interactive_message(self, to_phone: str, body: str, buttons: list[dict]) -> dict:
        """Send an interactive message with buttons."""
        button_list = []
        for btn in buttons[:3]:  # WhatsApp max 3 buttons
            button_list.append(
                {
                    "type": "reply",
                    "reply": {"id": btn["id"], "title": btn["title"][:20]},  # Max 20 chars
                }
            )

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone.replace("+", ""),
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body},
                "action": {"buttons": button_list},
            },
        }
        return self._send(payload)

    def _send(self, payload: dict) -> dict:
        """Send a message via WhatsApp API."""
        if not self.phone_number_id or not self.access_token:
            logger.warning("WhatsApp credentials not configured")
            return {"error": "WhatsApp not configured"}

        try:
            with httpx.Client(timeout=15) as client:
                response = client.post(self.messages_url, headers=self.headers, json=payload)
                response.raise_for_status()
                result = response.json()
                logger.info("WhatsApp message sent: %s", result.get("messages", [{}])[0].get("id", "unknown"))
                return result
        except httpx.HTTPStatusError as e:
            logger.error("WhatsApp API error %d: %s", e.response.status_code, e.response.text[:500])
            return {"error": str(e), "status_code": e.response.status_code}
        except Exception:
            logger.exception("WhatsApp API call failed")
            return {"error": "WhatsApp API call failed"}

    @staticmethod
    def verify_webhook_signature(payload_body: bytes, signature: str) -> bool:
        """Verify webhook signature from Meta."""
        app_secret = settings.WHATSAPP_APP_SECRET
        if not app_secret:
            logger.warning("WHATSAPP_APP_SECRET not configured, skipping verification")
            return True
        expected = hmac.new(app_secret.encode(), payload_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature)
