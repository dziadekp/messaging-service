"""
URL configuration for messaging_service project.
"""

from django.contrib import admin
from django.urls import include, path

from apps.core.views import PingView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.core.api_urls")),
    path("webhooks/", include("apps.core.webhook_urls")),
    path("ping/", PingView.as_view(), name="ping"),
]
