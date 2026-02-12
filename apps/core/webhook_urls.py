"""Webhook URL patterns for Messaging Service."""

from django.urls import path

from .views import whatsapp_webhook_view
from .views_telegram import telegram_webhook_view

urlpatterns = [
    path("whatsapp/", whatsapp_webhook_view, name="whatsapp_webhook"),
    path("telegram/", telegram_webhook_view, name="telegram_webhook"),
]
