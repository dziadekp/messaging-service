"""
Production settings for messaging_service.
"""

DEBUG = False

# Security settings
SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [r"^ping/$", r"^webhooks/"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
