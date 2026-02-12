"""Django admin for messaging service models."""

from django.contrib import admin

from .models import ConsentRecord, ContactProfile, Conversation, Message


@admin.register(ContactProfile)
class ContactProfileAdmin(admin.ModelAdmin):
    list_display = (
        "display_name",
        "phone_e164",
        "hub_team_id",
        "hub_client_id",
        "preferred_channel",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active", "preferred_channel", "created_at")
    search_fields = ("display_name", "phone_e164", "hub_team_id", "hub_client_id")
    readonly_fields = ("id", "created_at", "updated_at")
    ordering = ("-created_at",)

    fieldsets = (
        ("Contact Information", {"fields": ("id", "display_name", "phone_e164", "timezone")}),
        ("Hub Integration", {"fields": ("hub_team_id", "hub_client_id")}),
        ("Messaging Settings", {"fields": ("preferred_channel", "is_active")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(ConsentRecord)
class ConsentRecordAdmin(admin.ModelAdmin):
    list_display = (
        "contact",
        "consent_type",
        "channel",
        "consent_source",
        "consented_at",
        "created_at",
    )
    list_filter = ("consent_type", "consent_source", "channel", "consented_at")
    search_fields = (
        "contact__display_name",
        "contact__phone_e164",
        "notes",
    )
    readonly_fields = ("id", "created_at")
    ordering = ("-consented_at",)
    date_hierarchy = "consented_at"

    fieldsets = (
        ("Consent Details", {"fields": ("id", "contact", "channel", "consent_type")}),
        ("Source Information", {"fields": ("consent_source", "consented_at", "ip_address")}),
        ("Additional Information", {"fields": ("notes",)}),
        ("Timestamps", {"fields": ("created_at",)}),
    )


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "contact",
        "status",
        "current_state",
        "context_type",
        "channel",
        "last_activity_at",
        "created_at",
    )
    list_filter = ("status", "channel", "context_type", "created_at")
    search_fields = (
        "contact__display_name",
        "contact__phone_e164",
        "context_id",
        "current_state",
    )
    readonly_fields = ("id", "created_at", "updated_at", "last_activity_at")
    ordering = ("-last_activity_at",)
    date_hierarchy = "created_at"

    fieldsets = (
        ("Conversation Identity", {"fields": ("id", "contact", "channel")}),
        ("State Management", {"fields": ("status", "current_state", "state_data")}),
        ("Context Information", {"fields": ("context_type", "context_id", "context_data")}),
        ("Timing", {"fields": ("timeout_minutes", "last_activity_at", "created_at", "updated_at")}),
    )


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "conversation",
        "direction",
        "status",
        "template_name",
        "created_at",
        "delivered_at",
    )
    list_filter = ("direction", "status", "created_at")
    search_fields = (
        "conversation__contact__display_name",
        "conversation__contact__phone_e164",
        "body",
        "channel_message_id",
        "template_name",
    )
    readonly_fields = (
        "id",
        "created_at",
        "sent_at",
        "delivered_at",
        "read_at",
    )
    ordering = ("-created_at",)
    date_hierarchy = "created_at"

    fieldsets = (
        ("Message Identity", {"fields": ("id", "conversation", "direction")}),
        ("Content", {"fields": ("body", "template_name")}),
        ("Delivery Tracking", {"fields": ("status", "channel_message_id", "error_message")}),
        ("Timestamps", {"fields": ("created_at", "sent_at", "delivered_at", "read_at")}),
    )
