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
from .services.whatsapp_adapter import WhatsAppAdapter

logger = logging.getLogger(__name__)


class SendMessageView(APIView):
    """Send a message to a contact."""

    permission_classes = [HasServiceAPIKey]

    def post(self, request):
        serializer = SendMessageSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        contact_id = data["contact_id"]

        # Get contact
        try:
            contact = ContactProfile.objects.get(id=contact_id)
        except ContactProfile.DoesNotExist:
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

        # Create message record (standalone, no conversation)
        message = Message.objects.create(
            direction="outbound",
            body=data.get("body", ""),
            status="queued",
        )

        # Send via WhatsApp
        adapter = WhatsAppAdapter()
        try:
            if data.get("template_name"):
                result = adapter.send_template_message(
                    to_phone=contact.phone_e164,
                    template_name=data["template_name"],
                    params=data.get("template_params"),
                )
            else:
                result = adapter.send_text_message(
                    to_phone=contact.phone_e164,
                    body=data["body"],
                )

            if "error" in result:
                message.status = "failed"
                message.error_message = result.get("error", "Unknown error")
                message.save(update_fields=["status", "error_message"])
                return Response(
                    {"error": result["error"]},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            # Update message with WhatsApp message ID
            channel_message_id = result.get("messages", [{}])[0].get("id")
            message.channel_message_id = channel_message_id
            message.status = "sent"
            message.sent_at = now()
            message.save(update_fields=["channel_message_id", "status", "sent_at"])

            # Record rate limit
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
            logger.exception("Failed to send message")
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
        contact_id = data["contact_id"]

        # Get contact
        try:
            contact = ContactProfile.objects.get(id=contact_id)
        except ContactProfile.DoesNotExist:
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

        # Create conversation
        conversation = Conversation.objects.create(
            contact=contact,
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

        # Send via WhatsApp
        adapter = WhatsAppAdapter()
        try:
            buttons = data.get("buttons", [])
            if buttons:
                result = adapter.send_interactive_message(
                    to_phone=contact.phone_e164,
                    body=data["initial_message"],
                    buttons=buttons,
                )
            else:
                result = adapter.send_text_message(
                    to_phone=contact.phone_e164,
                    body=data["initial_message"],
                )

            if "error" in result:
                message.status = "failed"
                message.error_message = result.get("error", "Unknown error")
                message.save(update_fields=["status", "error_message"])
                conversation.status = "failed"
                conversation.save(update_fields=["status"])
                return Response(
                    {"error": result["error"]},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            # Update message with WhatsApp message ID
            channel_message_id = result.get("messages", [{}])[0].get("id")
            message.channel_message_id = channel_message_id
            message.status = "sent"
            message.sent_at = now()
            message.save(update_fields=["channel_message_id", "status", "sent_at"])

            # Transition conversation state
            state_machine = StateMachine()
            state_machine.transition(conversation, "on_send")

            # Record rate limit
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
            logger.exception("Failed to start conversation")
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

        # Get or create by hub_team_id + hub_client_id
        contact, created = ContactProfile.objects.get_or_create(
            hub_team_id=data["hub_team_id"],
            hub_client_id=data["hub_client_id"],
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
