"""API Key authentication for Hub → Messaging Service calls."""

import logging

from django.conf import settings
from rest_framework.permissions import BasePermission

logger = logging.getLogger(__name__)


class HasServiceAPIKey(BasePermission):
    """Check for valid API key in Authorization header."""

    def has_permission(self, request, view):
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith("Api-Key "):
            return False
        provided_key = auth_header[8:]
        expected_key = settings.MESSAGING_SERVICE_API_KEY
        if not expected_key:
            logger.warning("MESSAGING_SERVICE_API_KEY not configured")
            return False
        return provided_key == expected_key
