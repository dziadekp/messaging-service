"""Messaging service models."""

import uuid

from django.db import models


class ContactProfile(models.Model):
    """Contact that can receive messages. Linked to Hub via IDs (NOT ForeignKeys)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    hub_team_id = models.CharField(max_length=50, db_index=True)
    hub_client_id = models.CharField(max_length=50, db_index=True)
    phone_e164 = models.CharField(max_length=20, db_index=True)  # +15615551234
    display_name = models.CharField(max_length=255)
    preferred_channel = models.CharField(max_length=20, default="whatsapp")
    timezone = models.CharField(max_length=50, default="America/New_York")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("hub_team_id", "hub_client_id")]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.display_name} ({self.phone_e164})"


class ConsentRecord(models.Model):
    """TCPA consent tracking."""

    class ConsentType(models.TextChoices):
        OPT_IN = "opt_in", "Opt In"
        OPT_OUT = "opt_out", "Opt Out"
        REVOKED = "revoked", "Revoked"

    class ConsentSource(models.TextChoices):
        WEB_FORM = "web_form", "Web Form"
        WHATSAPP_REPLY = "whatsapp_reply", "WhatsApp Reply"
        API = "api", "API"
        MANUAL = "manual", "Manual"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contact = models.ForeignKey(ContactProfile, on_delete=models.CASCADE, related_name="consents")
    channel = models.CharField(max_length=20, default="whatsapp")
    consent_type = models.CharField(max_length=30, choices=ConsentType.choices)
    consent_source = models.CharField(max_length=50, choices=ConsentSource.choices)
    consented_at = models.DateTimeField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-consented_at"]

    def __str__(self):
        return f"{self.contact.display_name} - {self.consent_type} ({self.channel})"


class Conversation(models.Model):
    """Conversation thread with state machine."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        WAITING_REPLY = "waiting_reply", "Waiting for Reply"
        TIMED_OUT = "timed_out", "Timed Out"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contact = models.ForeignKey(ContactProfile, on_delete=models.CASCADE, related_name="conversations")
    channel = models.CharField(max_length=20, default="whatsapp")
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.ACTIVE)
    current_state = models.CharField(max_length=50, default="initial")
    state_data = models.JSONField(default=dict, blank=True)
    context_type = models.CharField(max_length=50, blank=True)  # clarification, digest, reminder
    context_id = models.CharField(max_length=100, blank=True, db_index=True)  # Hub object ID
    context_data = models.JSONField(default=dict, blank=True)
    last_activity_at = models.DateTimeField(auto_now=True)
    timeout_minutes = models.PositiveIntegerField(default=1440)  # 24h default
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_activity_at"]

    def __str__(self):
        return f"Conversation {self.id} ({self.status})"

    @property
    def is_active(self):
        return self.status in (self.Status.ACTIVE, self.Status.WAITING_REPLY)


class Message(models.Model):
    """Individual message in a conversation."""

    class Direction(models.TextChoices):
        INBOUND = "inbound", "Inbound"
        OUTBOUND = "outbound", "Outbound"

    class DeliveryStatus(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENT = "sent", "Sent"
        DELIVERED = "delivered", "Delivered"
        READ = "read", "Read"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
        null=True,
        blank=True,
    )
    direction = models.CharField(max_length=10, choices=Direction.choices)
    body = models.TextField()
    channel_message_id = models.CharField(max_length=255, blank=True, db_index=True)
    template_name = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=DeliveryStatus.choices, default=DeliveryStatus.QUEUED)
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.direction} message in {self.conversation_id}"
