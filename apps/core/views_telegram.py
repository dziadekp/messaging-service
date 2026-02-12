"""Telegram webhook view for Messaging Service."""

import json
import logging

from django.conf import settings
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .models import ContactProfile, Conversation, Message
from .services.hub_callback import HubCallbackService
from .services.state_machine import StateMachine
from .services.telegram_adapter import TelegramAdapter

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class TelegramWebhookView(View):
    """Handle Telegram Bot API webhook updates."""

    def post(self, request):
        """Process incoming Telegram update."""
        # Validate secret token header (set via setWebhook secret_token param)
        secret = request.META.get("HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN", "")
        expected = settings.TELEGRAM_WEBHOOK_SECRET
        if expected and secret != expected:
            logger.warning("Invalid Telegram webhook secret")
            return HttpResponse("Forbidden", status=403)

        try:
            update = json.loads(request.body)
        except json.JSONDecodeError:
            logger.error("Invalid JSON in Telegram webhook")
            return HttpResponse("Invalid JSON", status=400)

        try:
            if "message" in update:
                self._process_message(update["message"])
            elif "callback_query" in update:
                self._process_callback_query(update["callback_query"])
            else:
                logger.debug("Ignoring Telegram update type: %s", list(update.keys()))

            return HttpResponse("OK", status=200)
        except Exception:
            logger.exception("Error processing Telegram update")
            return HttpResponse("Error", status=500)

    def _process_message(self, message: dict):
        """Process an incoming Telegram text message."""
        chat = message.get("chat", {})
        chat_id = chat.get("id")
        text = message.get("text", "")

        if not chat_id:
            return

        # Handle /start command — log the chat_id for setup
        if text.strip().startswith("/start"):
            logger.info("Telegram /start from chat_id=%s, username=%s", chat_id, chat.get("username", ""))
            return

        # Find contact by telegram_chat_id
        try:
            contact = ContactProfile.objects.get(telegram_chat_id=chat_id)
        except ContactProfile.DoesNotExist:
            logger.warning("Telegram message from unknown chat_id=%s", chat_id)
            return

        # Check for opt-out
        if text.strip().upper() in ("STOP", "UNSUBSCRIBE", "CANCEL", "/STOP"):
            self._handle_opt_out(contact)
            return

        # Create inbound message
        telegram_message_id = str(message.get("message_id", ""))
        inbound_message = Message.objects.create(
            direction="inbound",
            body=text,
            channel_message_id=telegram_message_id,
            status="received",
        )

        # Find active conversation
        active_conversation = (
            Conversation.objects.filter(
                contact=contact,
                status__in=["active", "waiting_reply"],
            )
            .order_by("-created_at")
            .first()
        )

        if active_conversation:
            inbound_message.conversation = active_conversation
            inbound_message.save(update_fields=["conversation"])

            state_machine = StateMachine()
            state_machine.transition(active_conversation, "on_reply")

            hub_callback = HubCallbackService()
            hub_callback.client_replied(
                conversation_id=str(active_conversation.id),
                contact_id=str(contact.id),
                reply_text=text,
                context_type=active_conversation.context_type,
                context_id=active_conversation.context_id,
            )
            logger.info("Telegram inbound processed for conversation %s", active_conversation.id)
        else:
            logger.info("Telegram inbound without active conversation from chat_id=%s", chat_id)

    def _process_callback_query(self, callback_query: dict):
        """Process a Telegram inline keyboard button press."""
        callback_query_id = callback_query.get("id", "")
        chat = callback_query.get("message", {}).get("chat", {})
        chat_id = chat.get("id")
        data = callback_query.get("data", "")

        # Always answer the callback query to dismiss the loading spinner
        adapter = TelegramAdapter()
        if callback_query_id:
            result = adapter.answer_callback_query(callback_query_id)
            print(f"[TELEGRAM] answerCallbackQuery id={callback_query_id} result={result}", flush=True)

        if not chat_id:
            return

        # Send a confirmation reply so the user sees their selection
        if chat_id and data:
            reply_result = adapter.send_text_message(chat_id=chat_id, body=f"You selected: {data}")
            print(f"[TELEGRAM] confirmation reply chat_id={chat_id} data={data} result={reply_result}", flush=True)

        try:
            contact = ContactProfile.objects.get(telegram_chat_id=chat_id)
        except ContactProfile.DoesNotExist:
            logger.warning("Telegram callback from unknown chat_id=%s", chat_id)
            return

        # Create inbound message for the button press
        inbound_message = Message.objects.create(
            direction="inbound",
            body=data,
            channel_message_id=str(callback_query.get("id", "")),
            status="received",
        )

        # Find active conversation
        active_conversation = (
            Conversation.objects.filter(
                contact=contact,
                status__in=["active", "waiting_reply"],
            )
            .order_by("-created_at")
            .first()
        )

        if active_conversation:
            inbound_message.conversation = active_conversation
            inbound_message.save(update_fields=["conversation"])

            state_machine = StateMachine()
            state_machine.transition(active_conversation, "on_reply")

            hub_callback = HubCallbackService()
            hub_callback.client_replied(
                conversation_id=str(active_conversation.id),
                contact_id=str(contact.id),
                reply_text=data,
                context_type=active_conversation.context_type,
                context_id=active_conversation.context_id,
            )
            logger.info("Telegram callback processed for conversation %s", active_conversation.id)
        else:
            logger.info("Telegram callback without active conversation from chat_id=%s", chat_id)

    def _handle_opt_out(self, contact: ContactProfile):
        """Handle contact opting out."""
        contact.is_active = False
        contact.save(update_fields=["is_active"])

        hub_callback = HubCallbackService()
        hub_callback.client_opted_out(str(contact.id), contact.phone_e164)

        logger.info("Telegram contact %s opted out", contact.id)


telegram_webhook_view = TelegramWebhookView.as_view()
