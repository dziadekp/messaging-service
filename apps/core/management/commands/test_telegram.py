"""Test sending a Telegram message."""

from django.core.management.base import BaseCommand

from apps.core.services.telegram_adapter import TelegramAdapter


class Command(BaseCommand):
    help = "Send a test Telegram message to verify bot configuration"

    def add_arguments(self, parser):
        parser.add_argument("chat_id", type=int, help="Telegram chat ID to send to")
        parser.add_argument("message", type=str, nargs="?", default="Hello from TransactionFlow!", help="Message text")
        parser.add_argument("--buttons", action="store_true", help="Include test inline keyboard buttons")

    def handle(self, *args, **options):
        adapter = TelegramAdapter()

        # Verify bot first
        self.stdout.write("Verifying bot token...")
        me = adapter.get_me()
        if not me.get("ok"):
            self.stderr.write(self.style.ERROR(f"Bot token invalid: {me}"))
            return

        bot_info = me["result"]
        self.stdout.write(self.style.SUCCESS(f"Bot: @{bot_info.get('username')} ({bot_info.get('first_name')})"))

        chat_id = options["chat_id"]
        message = options["message"]

        if options["buttons"]:
            buttons = [
                {"id": "btn_yes", "title": "Yes"},
                {"id": "btn_no", "title": "No"},
                {"id": "btn_later", "title": "Remind me later"},
            ]
            self.stdout.write(f"Sending interactive message to chat_id={chat_id}...")
            result = adapter.send_interactive_message(chat_id=chat_id, body=message, buttons=buttons)
        else:
            self.stdout.write(f"Sending text message to chat_id={chat_id}...")
            result = adapter.send_text_message(chat_id=chat_id, body=message)

        if result.get("ok"):
            msg_id = result["result"]["message_id"]
            self.stdout.write(self.style.SUCCESS(f"Message sent! message_id={msg_id}"))
        else:
            self.stderr.write(self.style.ERROR(f"Send failed: {result}"))
