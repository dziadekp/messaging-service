"""Callback service for notifying Hub of messaging events."""

import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


class HubCallbackService:
    """Send event callbacks to Hub webhook endpoint."""

    def __init__(self):
        self.webhook_url = settings.HUB_WEBHOOK_URL
        self.webhook_secret = settings.HUB_WEBHOOK_SECRET

    def notify(self, event_type: str, payload: dict) -> bool:
        """Send event to Hub. Returns True on success."""
        if not self.webhook_url:
            logger.warning("HUB_WEBHOOK_URL not configured, skipping callback")
            return False

        data = {
            "event_type": event_type,
            "payload": payload,
        }
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Secret": self.webhook_secret or "",
        }

        try:
            with httpx.Client(timeout=10) as client:
                response = client.post(self.webhook_url, json=data, headers=headers)
                response.raise_for_status()
                logger.info("Hub callback sent: %s -> %d", event_type, response.status_code)
                return True
        except Exception:
            logger.exception("Hub callback failed: %s", event_type)
            return False

    def client_replied(
        self,
        conversation_id: str,
        contact_id: str,
        reply_text: str,
        context_type: str,
        context_id: str,
    ):
        """Notify Hub that a client replied to a message."""
        return self.notify(
            "client.replied",
            {
                "conversation_id": conversation_id,
                "contact_id": contact_id,
                "reply_text": reply_text,
                "context_type": context_type,
                "context_id": context_id,
            },
        )

    def delivery_status_changed(self, message_id: str, status: str):
        """Notify Hub of delivery status change."""
        return self.notify(
            "message.status_changed",
            {
                "message_id": message_id,
                "status": status,
            },
        )

    def client_opted_out(self, contact_id: str, phone: str):
        """Notify Hub that client opted out (sent STOP)."""
        return self.notify(
            "contact.opted_out",
            {
                "contact_id": contact_id,
                "phone": phone,
            },
        )
