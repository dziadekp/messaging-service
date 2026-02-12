"""Core views for Messaging Service."""

import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.utils.timezone import now
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .models import ContactProfile, Conversation, Message
from .services.hub_callback import HubCallbackService
from .services.state_machine import StateMachine

logger = logging.getLogger(__name__)


class PingView(View):
    """Health check endpoint."""

    def get(self, request):
        return JsonResponse({"status": "pong"}, status=200)


@method_decorator(csrf_exempt, name="dispatch")
class WhatsAppWebhookView(View):
    """Handle WhatsApp webhook verification and incoming events."""

    def get(self, request):
        """Verify webhook registration."""
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")

        verify_token = settings.WHATSAPP_VERIFY_TOKEN

        if mode == "subscribe" and token == verify_token:
            logger.info("WhatsApp webhook verified")
            return HttpResponse(challenge, status=200)

        logger.warning("WhatsApp webhook verification failed")
        return HttpResponse("Verification failed", status=403)

    def post(self, request):
        """Process incoming WhatsApp events."""
        # Validate signature
        signature = request.META.get("HTTP_X_HUB_SIGNATURE_256", "")
        if not self._verify_signature(request.body, signature):
            logger.warning("Invalid webhook signature")
            return HttpResponse("Invalid signature", status=403)

        # Parse payload
        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            logger.error("Invalid JSON payload")
            return HttpResponse("Invalid JSON", status=400)

        # Process webhook events
        try:
            self._process_webhook_events(payload)
            return HttpResponse("OK", status=200)
        except Exception:
            logger.exception("Error processing webhook events")
            return HttpResponse("Error processing events", status=500)

    def _verify_signature(self, payload_body: bytes, signature: str) -> bool:
        """Verify webhook signature from Meta."""
        app_secret = settings.WHATSAPP_APP_SECRET
        if not app_secret:
            logger.warning("WHATSAPP_APP_SECRET not configured, skipping verification")
            return True

        expected = hmac.new(app_secret.encode(), payload_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature)

    def _process_webhook_events(self, payload: dict):
        """Process webhook events from WhatsApp."""
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})

                # Process status updates
                for status_update in value.get("statuses", []):
                    self._process_status_update(status_update)

                # Process incoming messages
                for message in value.get("messages", []):
                    self._process_inbound_message(message, value.get("metadata", {}))

    def _process_status_update(self, status_update: dict):
        """Update message delivery status."""
        channel_message_id = status_update.get("id")
        new_status = status_update.get("status")

        if not channel_message_id or not new_status:
            return

        try:
            message = Message.objects.get(channel_message_id=channel_message_id)
        except Message.DoesNotExist:
            logger.warning("Status update for unknown message: %s", channel_message_id)
            return

        # Map WhatsApp status to our status
        status_mapping = {
            "sent": "sent",
            "delivered": "delivered",
            "read": "read",
            "failed": "failed",
        }
        mapped_status = status_mapping.get(new_status)

        if mapped_status:
            message.status = mapped_status

            if mapped_status == "delivered" and not message.delivered_at:
                message.delivered_at = now()
            elif mapped_status == "read" and not message.read_at:
                message.read_at = now()
            elif mapped_status == "failed":
                error = status_update.get("errors", [{}])[0]
                message.error_message = error.get("message", "Unknown error")

            message.save(update_fields=["status", "delivered_at", "read_at", "error_message"])

            # Notify Hub
            hub_callback = HubCallbackService()
            hub_callback.delivery_status_changed(str(message.id), mapped_status)

            logger.info("Message %s status updated to %s", channel_message_id, mapped_status)

    def _process_inbound_message(self, message_data: dict, metadata: dict):
        """Process incoming message from contact."""
        from_phone = message_data.get("from", "").strip()
        channel_message_id = message_data.get("id")
        message_type = message_data.get("type")

        # Normalize phone to E.164
        if not from_phone.startswith("+"):
            from_phone = f"+{from_phone}"

        # Find contact
        try:
            contact = ContactProfile.objects.get(phone_e164=from_phone)
        except ContactProfile.DoesNotExist:
            logger.warning("Inbound message from unknown contact: %s", from_phone)
            return

        # Extract message body
        body = ""
        if message_type == "text":
            body = message_data.get("text", {}).get("body", "")
        elif message_type == "button":
            body = message_data.get("button", {}).get("text", "")
        elif message_type == "interactive":
            interactive = message_data.get("interactive", {})
            if interactive.get("type") == "button_reply":
                body = interactive.get("button_reply", {}).get("title", "")

        # Check for opt-out keywords
        if body.strip().upper() in ("STOP", "UNSUBSCRIBE", "CANCEL"):
            self._handle_opt_out(contact)
            return

        # Create inbound message record (conversation linked below if found)
        inbound_message = Message.objects.create(
            direction="inbound",
            body=body,
            channel_message_id=channel_message_id,
            status="received",
        )

        # Find active conversation for this contact
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

            # Update conversation state
            state_machine = StateMachine()
            state_machine.transition(active_conversation, "on_reply")

            # Notify Hub about the reply
            hub_callback = HubCallbackService()
            hub_callback.client_replied(
                conversation_id=str(active_conversation.id),
                contact_id=str(contact.id),
                reply_text=body,
                context_type=active_conversation.context_type,
                context_id=active_conversation.context_id,
            )

            logger.info("Inbound message processed for conversation %s", active_conversation.id)
        else:
            logger.info("Inbound message without active conversation from contact %s", contact.id)

    def _handle_opt_out(self, contact: ContactProfile):
        """Handle contact opting out via STOP keyword."""
        contact.is_active = False
        contact.save(update_fields=["is_active"])

        # Notify Hub
        hub_callback = HubCallbackService()
        hub_callback.client_opted_out(str(contact.id), contact.phone_e164)

        logger.info("Contact %s opted out", contact.id)


# Create instance for URL routing
whatsapp_webhook_view = WhatsAppWebhookView.as_view()
