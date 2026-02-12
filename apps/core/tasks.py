"""Celery tasks for messaging service."""

import logging
from datetime import timedelta

from celery import shared_task
from django.db.models import F
from django.db.models.functions import Now
from django.utils.timezone import now

from .models import ContactProfile, Conversation, Message
from .services.hub_callback import HubCallbackService
from .services.state_machine import StateMachine
from .services.whatsapp_adapter import WhatsAppAdapter

logger = logging.getLogger(__name__)


@shared_task
def check_conversation_timeouts():
    """
    Periodic task to check for timed-out conversations.
    Runs hourly via Celery Beat.
    """
    # Use DB-level expression: last_activity_at <= now() - (timeout_minutes * 1 minute)
    timed_out_conversations = Conversation.objects.filter(
        status="waiting_reply",
        last_activity_at__lte=Now() - F("timeout_minutes") * timedelta(minutes=1),
    ).select_related("contact")

    count = 0
    state_machine = StateMachine()
    hub_callback = HubCallbackService()

    for conversation in timed_out_conversations:
        # Transition to timed_out state
        new_state = state_machine.transition(conversation, "on_timeout")

        if new_state:
            # Notify Hub about timeout
            hub_callback.notify(
                "conversation.timed_out",
                {
                    "conversation_id": str(conversation.id),
                    "contact_id": str(conversation.contact.id),
                    "context_type": conversation.context_type,
                    "context_id": conversation.context_id,
                },
            )
            count += 1
            logger.info("Conversation %s timed out", conversation.id)

    logger.info("Checked conversation timeouts: %d conversations timed out", count)
    return count


@shared_task
def send_message_async(contact_id: str, body: str, template_name: str = None, template_params: dict = None):
    """
    Async task for sending messages via WhatsApp adapter.
    Used by views to avoid blocking requests.
    """
    try:
        contact = ContactProfile.objects.get(id=contact_id)
    except ContactProfile.DoesNotExist:
        logger.error("Contact %s not found for async message send", contact_id)
        return {"error": "Contact not found"}

    # Create message record (standalone, no conversation)
    message = Message.objects.create(
        direction="outbound",
        body=body or "",
        status="queued",
    )

    # Send via WhatsApp
    adapter = WhatsAppAdapter()
    try:
        if template_name:
            result = adapter.send_template_message(
                to_phone=contact.phone_e164,
                template_name=template_name,
                params=template_params,
            )
        else:
            result = adapter.send_text_message(
                to_phone=contact.phone_e164,
                body=body,
            )

        if "error" in result:
            message.status = "failed"
            message.error_message = result.get("error", "Unknown error")
            message.save(update_fields=["status", "error_message"])
            logger.error("Async message send failed: %s", result["error"])
            return {"error": result["error"]}

        # Update message with WhatsApp message ID
        channel_message_id = result.get("messages", [{}])[0].get("id")
        message.channel_message_id = channel_message_id
        message.status = "sent"
        message.sent_at = now()
        message.save(update_fields=["channel_message_id", "status", "sent_at"])

        logger.info("Async message sent: %s", message.id)
        return {"message_id": str(message.id), "status": "sent"}

    except Exception as e:
        logger.exception("Failed to send async message")
        message.status = "failed"
        message.error_message = str(e)
        message.save(update_fields=["status", "error_message"])
        return {"error": str(e)}
