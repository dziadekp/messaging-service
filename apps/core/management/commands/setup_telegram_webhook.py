"""Register Telegram webhook with Bot API."""

import os

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.core.services.telegram_adapter import TelegramAdapter


class Command(BaseCommand):
    help = "Register the Telegram webhook URL with the Bot API"

    def add_arguments(self, parser):
        parser.add_argument("--url", type=str, help="Override webhook URL (auto-detected from RAILWAY_PUBLIC_DOMAIN)")
        parser.add_argument("--delete", action="store_true", help="Delete the webhook instead of setting it")

    def handle(self, *args, **options):
        adapter = TelegramAdapter()

        if not settings.TELEGRAM_BOT_TOKEN:
            self.stderr.write(self.style.ERROR("TELEGRAM_BOT_TOKEN not configured"))
            return

        # Verify bot first
        me = adapter.get_me()
        if not me.get("ok"):
            self.stderr.write(self.style.ERROR(f"Bot token invalid: {me}"))
            return

        bot_info = me["result"]
        self.stdout.write(f"Bot: @{bot_info.get('username')} ({bot_info.get('first_name')})")

        if options["delete"]:
            result = adapter.delete_webhook()
            if result.get("ok"):
                self.stdout.write(self.style.SUCCESS("Webhook deleted"))
            else:
                self.stderr.write(self.style.ERROR(f"Failed to delete webhook: {result}"))
            return

        # Determine webhook URL
        webhook_url = options.get("url")
        if not webhook_url:
            domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
            if domain:
                webhook_url = f"https://{domain}/webhooks/telegram/"
            else:
                self.stderr.write(
                    self.style.ERROR("Cannot auto-detect URL. Provide --url or set RAILWAY_PUBLIC_DOMAIN")
                )
                return

        self.stdout.write(f"Setting webhook to: {webhook_url}")
        if settings.TELEGRAM_WEBHOOK_SECRET:
            self.stdout.write("Secret token: configured")
        else:
            self.stdout.write(self.style.WARNING("No TELEGRAM_WEBHOOK_SECRET set — webhook will be unprotected"))

        result = adapter.set_webhook(webhook_url)
        if result.get("ok"):
            self.stdout.write(self.style.SUCCESS(f"Webhook registered: {result.get('description', 'ok')}"))
        else:
            self.stderr.write(self.style.ERROR(f"Failed to set webhook: {result}"))
