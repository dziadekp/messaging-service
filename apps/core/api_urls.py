"""API URL patterns for Messaging Service."""

from django.urls import path

from .api_views import (
    ConversationStatusView,
    CreateContactView,
    RecordConsentView,
    SendMessageView,
    StartConversationView,
)

urlpatterns = [
    path("send/", SendMessageView.as_view(), name="send_message"),
    path("conversations/start/", StartConversationView.as_view(), name="start_conversation"),
    path("conversations/<uuid:conversation_id>/", ConversationStatusView.as_view(), name="conversation_status"),
    path("contacts/", CreateContactView.as_view(), name="create_contact"),
    path("consent/", RecordConsentView.as_view(), name="record_consent"),
]
