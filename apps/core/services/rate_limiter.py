"""Per-contact rate limiting."""

import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate limit messages per contact to prevent spam."""

    MAX_MESSAGES_PER_HOUR = 10
    MAX_MESSAGES_PER_DAY = 30

    def check(self, contact_id: str) -> tuple[bool, str]:
        """Check if contact can receive a message. Returns (allowed, reason)."""
        hourly_key = f"msg_rate:{contact_id}:hourly"
        daily_key = f"msg_rate:{contact_id}:daily"

        hourly_count = cache.get(hourly_key, 0)
        if hourly_count >= self.MAX_MESSAGES_PER_HOUR:
            return False, f"Hourly limit ({self.MAX_MESSAGES_PER_HOUR}) exceeded"

        daily_count = cache.get(daily_key, 0)
        if daily_count >= self.MAX_MESSAGES_PER_DAY:
            return False, f"Daily limit ({self.MAX_MESSAGES_PER_DAY}) exceeded"

        return True, ""

    def record(self, contact_id: str):
        """Record a sent message for rate limiting."""
        hourly_key = f"msg_rate:{contact_id}:hourly"
        daily_key = f"msg_rate:{contact_id}:daily"

        hourly_count = cache.get(hourly_key, 0)
        cache.set(hourly_key, hourly_count + 1, timeout=3600)

        daily_count = cache.get(daily_key, 0)
        cache.set(daily_key, daily_count + 1, timeout=86400)
