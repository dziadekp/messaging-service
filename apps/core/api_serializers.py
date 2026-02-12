"""DRF serializers for Messaging Service API."""

from rest_framework import serializers

from .models import ConsentRecord, ContactProfile, Conversation, Message


class ContactSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating contacts."""

    class Meta:
        model = ContactProfile
        fields = [
            "id",
            "hub_team_id",
            "hub_client_id",
            "contact_type",
            "phone_e164",
            "telegram_chat_id",
            "display_name",
            "preferred_channel",
            "timezone",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_phone_e164(self, value):
        """Validate E.164 format (optional — can be empty for Telegram-only contacts)."""
        if not value:
            return value
        if not value.startswith("+"):
            raise serializers.ValidationError("Phone must be in E.164 format (e.g., +12345678900)")
        if not value[1:].isdigit():
            raise serializers.ValidationError("Phone must contain only digits after +")
        if len(value) < 10 or len(value) > 16:
            raise serializers.ValidationError("Phone must be 10-16 characters")
        return value


class ConsentSerializer(serializers.ModelSerializer):
    """Serializer for recording consent."""

    contact_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = ConsentRecord
        fields = [
            "id",
            "contact_id",
            "channel",
            "consent_type",
            "consent_source",
            "consented_at",
            "ip_address",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def create(self, validated_data):
        """Create consent record with contact lookup."""
        contact_id = validated_data.pop("contact_id")
        try:
            contact = ContactProfile.objects.get(id=contact_id)
        except ContactProfile.DoesNotExist:
            raise serializers.ValidationError({"contact_id": "Contact not found"})

        validated_data["contact"] = contact
        return super().create(validated_data)


class SendMessageSerializer(serializers.Serializer):
    """Serializer for sending a message."""

    contact_id = serializers.UUIDField(required=False)
    hub_team_id = serializers.CharField(max_length=50, required=False)
    hub_client_id = serializers.CharField(max_length=50, required=False, default="")
    body = serializers.CharField(max_length=4096, required=False)
    template_name = serializers.CharField(max_length=255, required=False)
    template_params = serializers.JSONField(required=False)

    def validate(self, data):
        """Ensure either body or template_name is provided."""
        if not data.get("body") and not data.get("template_name"):
            raise serializers.ValidationError("Either body or template_name must be provided")
        return data


class StartConversationSerializer(serializers.Serializer):
    """Serializer for starting a conversation."""

    # Contact lookup: either by UUID or by Hub IDs
    contact_id = serializers.UUIDField(required=False)
    hub_team_id = serializers.CharField(max_length=50, required=False)
    hub_client_id = serializers.CharField(max_length=50, required=False, default="")
    contact_type = serializers.ChoiceField(choices=["client", "accountant"], required=False, default="client")
    context_type = serializers.ChoiceField(
        choices=["clarification", "digest", "reminder", "monthly_call_defer", "accountant_digest", "weekly_batch"]
    )
    context_id = serializers.CharField(max_length=255)
    context_data = serializers.JSONField(required=False, default=dict)
    timeout_minutes = serializers.IntegerField(default=1440, min_value=1, max_value=10080)
    initial_message = serializers.CharField(max_length=4096)
    buttons = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        allow_empty=True,
    )

    def validate_buttons(self, value):
        """Validate button structure."""
        if not value:
            return value

        if len(value) > 3:
            raise serializers.ValidationError("Maximum 3 buttons allowed")

        for btn in value:
            if "id" not in btn or "title" not in btn:
                raise serializers.ValidationError("Each button must have 'id' and 'title'")
            if len(btn["title"]) > 20:
                raise serializers.ValidationError("Button title must be 20 characters or less")

        return value


class MessageSerializer(serializers.ModelSerializer):
    """Read-only serializer for messages."""

    class Meta:
        model = Message
        fields = [
            "id",
            "direction",
            "body",
            "status",
            "sent_at",
            "delivered_at",
            "read_at",
            "created_at",
        ]
        read_only_fields = fields


class ConversationStatusSerializer(serializers.ModelSerializer):
    """Read-only serializer for conversation status."""

    messages = MessageSerializer(many=True, read_only=True)

    class Meta:
        model = Conversation
        fields = [
            "id",
            "status",
            "current_state",
            "messages",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
