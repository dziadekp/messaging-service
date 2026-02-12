"""Telegram Bot API adapter."""

import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


class TelegramAdapter:
    """Client for Telegram Bot API."""

    BASE_URL = "https://api.telegram.org"

    def __init__(self):
        self.bot_token = settings.TELEGRAM_BOT_TOKEN

    @property
    def api_url(self):
        return f"{self.BASE_URL}/bot{self.bot_token}"

    def send_text_message(self, chat_id: int, body: str) -> dict:
        """Send a plain text message."""
        payload = {
            "chat_id": chat_id,
            "text": body,
            "parse_mode": "HTML",
        }
        return self._call("sendMessage", payload)

    def send_interactive_message(self, chat_id: int, body: str, buttons: list[dict]) -> dict:
        """Send a message with inline keyboard buttons."""
        keyboard = []
        for btn in buttons:
            keyboard.append([{"text": btn["title"], "callback_data": btn["id"]}])

        payload = {
            "chat_id": chat_id,
            "text": body,
            "parse_mode": "HTML",
            "reply_markup": {"inline_keyboard": keyboard},
        }
        return self._call("sendMessage", payload)

    def set_webhook(self, url: str) -> dict:
        """Register a webhook URL with Telegram."""
        payload = {
            "url": url,
            "secret_token": settings.TELEGRAM_WEBHOOK_SECRET,
            "allowed_updates": ["message", "callback_query"],
        }
        return self._call("setWebhook", payload)

    def delete_webhook(self) -> dict:
        """Remove the webhook."""
        return self._call("deleteWebhook", {})

    def get_me(self) -> dict:
        """Verify bot token and get bot info."""
        return self._call("getMe", {})

    def _call(self, method: str, payload: dict) -> dict:
        """Make a Telegram Bot API call."""
        if not self.bot_token:
            logger.warning("Telegram bot token not configured")
            return {"ok": False, "error": "Telegram not configured"}

        url = f"{self.api_url}/{method}"
        try:
            with httpx.Client(timeout=15) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                result = response.json()
                if result.get("ok"):
                    logger.info("Telegram %s success", method)
                else:
                    logger.warning("Telegram %s returned ok=false: %s", method, result.get("description"))
                return result
        except httpx.HTTPStatusError as e:
            logger.error("Telegram API error %d: %s", e.response.status_code, e.response.text[:500])
            return {"ok": False, "error": str(e), "status_code": e.response.status_code}
        except Exception:
            logger.exception("Telegram API call failed: %s", method)
            return {"ok": False, "error": f"Telegram API call failed: {method}"}
