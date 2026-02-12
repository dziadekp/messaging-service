"""DRF API views for Messaging Service."""

import logging

from django.utils.timezone import now
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .api_serializers import (
    ConsentSerializer,
    ContactSerializer,
    ConversationStatusSerializer,
    SendMessageSerializer,
    StartConversationSerializer,
)
from .middleware.auth import HasServiceAPIKey
from .models import ContactProfile, Conversation, Message
from .services.rate_limiter import RateLimiter
from .services.state_machine import StateMachine
from .services.telegram_adapter import TelegramAdapter
from .services.whatsapp_adapter import WhatsAppAdapter

logger = logging.getLogger(__name__)


def _get_adapter(contact):
    """Return the appropriate messaging adapter for a contact."""
    if contact.preferred_channel == "telegram":
        return TelegramAdapter(), "telegram"
    return WhatsAppAdapter(), "whatsapp"


def _get_recipient(contact, channel):
    """Return the recipient identifier for the given channel."""
    if channel == "telegram":
        if not contact.telegram_chat_id:
            return None
        return contact.telegram_chat_id
    return contact.phone_e164


class SendMessageView(APIView):
    """Send a message to a contact."""

    permission_classes = [HasServiceAPIKey]

    def post(self, request):
        serializer = SendMessageSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        # Resolve contact: by UUID or by Hub IDs
        contact = None
        if data.get("contact_id"):
            try:
                contact = ContactProfile.objects.get(id=data["contact_id"])
            except ContactProfile.DoesNotExist:
                pass
        elif data.get("hub_team_id"):
            contact = ContactProfile.objects.filter(
                hub_team_id=data["hub_team_id"],
                hub_client_id=data.get("hub_client_id", ""),
            ).first()

        if contact is None:
            return Response(
                {"error": "Contact not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Rate limiting
        rate_limiter = RateLimiter()
        allowed, reason = rate_limiter.check(str(contact.id))
        if not allowed:
            return Response(
                {"error": f"Rate limit exceeded: {reason}"},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # Determine channel and adapter
        adapter, channel = _get_adapter(contact)
        recipient = _get_recipient(contact, channel)
        if recipient is None:
            return Response(
                {"error": f"Contact has no {channel} address configured"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create message record (standalone, no conversation)
        message = Message.objects.create(
            direction="outbound",
            body=data.get("body", ""),
            status="queued",
        )

        # Send via selected channel
        try:
            if channel == "telegram":
                result = adapter.send_text_message(chat_id=recipient, body=data["body"])
                has_error = not result.get("ok", False)
                error_msg = result.get("error", result.get("description", "Unknown error"))
                channel_message_id = str(result.get("result", {}).get("message_id", "")) if not has_error else ""
            else:
                # WhatsApp
                if data.get("template_name"):
                    result = adapter.send_template_message(
                        to_phone=recipient,
                        template_name=data["template_name"],
                        params=data.get("template_params"),
                    )
                else:
                    result = adapter.send_text_message(to_phone=recipient, body=data["body"])
                has_error = "error" in result
                error_msg = result.get("error", "Unknown error")
                channel_message_id = result.get("messages", [{}])[0].get("id", "") if not has_error else ""

            if has_error:
                message.status = "failed"
                message.error_message = error_msg
                message.save(update_fields=["status", "error_message"])
                return Response({"error": error_msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            message.channel_message_id = channel_message_id
            message.status = "sent"
            message.sent_at = now()
            message.save(update_fields=["channel_message_id", "status", "sent_at"])

            rate_limiter.record(str(contact.id))

            return Response(
                {
                    "message_id": str(message.id),
                    "status": message.status,
                    "channel_message_id": channel_message_id,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.exception("Failed to send message via %s", channel)
            message.status = "failed"
            message.error_message = str(e)
            message.save(update_fields=["status", "error_message"])
            return Response(
                {"error": "Failed to send message"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class StartConversationView(APIView):
    """Start a conversation with a contact."""

    permission_classes = [HasServiceAPIKey]

    def post(self, request):
        serializer = StartConversationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        # Resolve contact: by UUID or by Hub IDs
        contact = None
        if data.get("contact_id"):
            try:
                contact = ContactProfile.objects.get(id=data["contact_id"])
            except ContactProfile.DoesNotExist:
                pass
        elif data.get("hub_team_id"):
            contact = ContactProfile.objects.filter(
                hub_team_id=data["hub_team_id"],
                hub_client_id=data.get("hub_client_id", ""),
                contact_type=data.get("contact_type", "client"),
            ).first()

        if contact is None:
            return Response(
                {"error": "Contact not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Rate limiting
        rate_limiter = RateLimiter()
        allowed, reason = rate_limiter.check(str(contact.id))
        if not allowed:
            return Response(
                {"error": f"Rate limit exceeded: {reason}"},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # Determine channel and adapter
        adapter, channel = _get_adapter(contact)
        recipient = _get_recipient(contact, channel)
        if recipient is None:
            return Response(
                {"error": f"Contact has no {channel} address configured"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create conversation
        conversation = Conversation.objects.create(
            contact=contact,
            channel=channel,
            context_type=data["context_type"],
            context_id=data["context_id"],
            context_data=data.get("context_data", {}),
            timeout_minutes=data["timeout_minutes"],
            current_state="initial",
            status="active",
        )

        # Create initial message
        message = Message.objects.create(
            conversation=conversation,
            direction="outbound",
            body=data["initial_message"],
            status="queued",
        )

        # Send via selected channel
        try:
            buttons = data.get("buttons", [])
            if channel == "telegram":
                if buttons:
                    result = adapter.send_interactive_message(
                        chat_id=recipient, body=data["initial_message"], buttons=buttons
                    )
                else:
                    result = adapter.send_text_message(chat_id=recipient, body=data["initial_message"])
                has_error = not result.get("ok", False)
                error_msg = result.get("error", result.get("description", "Unknown error"))
                channel_message_id = str(result.get("result", {}).get("message_id", "")) if not has_error else ""
            else:
                # WhatsApp
                if buttons:
                    result = adapter.send_interactive_message(
                        to_phone=recipient, body=data["initial_message"], buttons=buttons
                    )
                else:
                    result = adapter.send_text_message(to_phone=recipient, body=data["initial_message"])
                has_error = "error" in result
                error_msg = result.get("error", "Unknown error")
                channel_message_id = result.get("messages", [{}])[0].get("id", "") if not has_error else ""

            if has_error:
                message.status = "failed"
                message.error_message = error_msg
                message.save(update_fields=["status", "error_message"])
                conversation.status = "failed"
                conversation.save(update_fields=["status"])
                return Response({"error": error_msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            message.channel_message_id = channel_message_id
            message.status = "sent"
            message.sent_at = now()
            message.save(update_fields=["channel_message_id", "status", "sent_at"])

            state_machine = StateMachine()
            state_machine.transition(conversation, "on_send")

            rate_limiter.record(str(contact.id))

            return Response(
                {
                    "conversation_id": str(conversation.id),
                    "status": conversation.status,
                    "current_state": conversation.current_state,
                    "message_id": str(message.id),
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            logger.exception("Failed to start conversation via %s", channel)
            message.status = "failed"
            message.error_message = str(e)
            message.save(update_fields=["status", "error_message"])
            conversation.status = "failed"
            conversation.save(update_fields=["status"])
            return Response(
                {"error": "Failed to start conversation"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ConversationStatusView(APIView):
    """Get conversation status and messages."""

    permission_classes = [HasServiceAPIKey]

    def get(self, request, conversation_id):
        try:
            conversation = Conversation.objects.prefetch_related("messages").get(id=conversation_id)
        except Conversation.DoesNotExist:
            return Response(
                {"error": "Conversation not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = ConversationStatusSerializer(conversation)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CreateContactView(APIView):
    """Create or update a contact."""

    permission_classes = [HasServiceAPIKey]

    def post(self, request):
        serializer = ContactSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        # Get or create by hub_team_id + hub_client_id + contact_type
        contact_type = data.get("contact_type", "client")
        contact, created = ContactProfile.objects.get_or_create(
            hub_team_id=data["hub_team_id"],
            hub_client_id=data.get("hub_client_id", ""),
            contact_type=contact_type,
            defaults=data,
        )

        # Update if exists
        if not created:
            for key, value in data.items():
                setattr(contact, key, value)
            contact.save()

        response_serializer = ContactSerializer(contact)
        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class RecordConsentView(APIView):
    """Record consent for a contact."""

    permission_classes = [HasServiceAPIKey]

    def post(self, request):
        serializer = ConsentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        consent = serializer.save()
        response_serializer = ConsentSerializer(consent)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
