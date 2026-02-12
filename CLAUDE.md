# messaging-service

WhatsApp messaging platform service for the Open Mind Transaction Flow ecosystem.

## Overview

This service provides WhatsApp messaging capabilities via the Meta Cloud API. It follows the same deployment pattern as the ai-translator service and is deployed to Railway.

## Architecture

- **Framework**: Django 5.1+ with Django REST Framework
- **Task Queue**: Celery with Redis
- **Database**: PostgreSQL (Railway)
- **Deployment**: Railway (Dockerfile-based)
- **Authentication**: API Key header (`Api-Key: <token>`)

## Key Endpoints

### API Endpoints (`/api/v1/`)
- `POST /api/v1/messages/send/` - Send WhatsApp message
- `GET /api/v1/messages/status/{message_id}/` - Check message status

### Webhook Endpoints (`/webhooks/`)
- `GET /webhooks/whatsapp/` - WhatsApp webhook verification
- `POST /webhooks/whatsapp/` - WhatsApp incoming message/status webhook

### Health Check
- `GET /ping/` - Health check endpoint (returns 200 OK)

## Authentication

All API endpoints require an `Api-Key` header:

```
Api-Key: <MESSAGING_SERVICE_API_KEY>
```

Webhooks use WhatsApp verification tokens and app secret for validation.

## Configuration

Required environment variables:

- `SECRET_KEY` - Django secret key
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection string
- `MESSAGING_SERVICE_API_KEY` - API key for service-to-service auth
- `WHATSAPP_PHONE_NUMBER_ID` - Meta Cloud API phone number ID
- `WHATSAPP_ACCESS_TOKEN` - Meta Cloud API access token
- `WHATSAPP_VERIFY_TOKEN` - Webhook verification token
- `WHATSAPP_APP_SECRET` - WhatsApp app secret for signature validation
- `HUB_WEBHOOK_URL` - Hub callback URL for message events
- `HUB_WEBHOOK_SECRET` - Shared secret for Hub webhook auth
- `HEALTH_CHECK_TOKENS` - Comma-separated list of valid health check tokens (optional)

## Deployment

### Railway Deployment

This service follows the same Railway deployment pattern as ai-translator:

1. Push to `main` branch triggers auto-deploy
2. Railway builds using Dockerfile
3. Health check on `/ping/` (300s timeout)
4. Migrations run automatically on deploy

### Local Development

```bash
uv sync
source .venv/bin/activate
python manage.py migrate
python manage.py runserver
```

## Integration with Hub

The Hub (`open_mind_transac`) calls this service to send WhatsApp messages. This service webhooks back to the Hub with message status updates and incoming messages.

**Hub → Messaging Service**: HTTP API with Api-Key auth
**Messaging Service → Hub**: Webhook with shared secret auth

## Hub-Leg Architecture Note

This is a **platform capability service**, not a Hub-Leg component. It provides messaging infrastructure for the entire ecosystem but does not handle billing, entitlements, or business logic. Those remain in the Hub.

## Cost Optimization

- Single web worker (Gunicorn with 2 workers, 2 threads)
- Celery worker runs separately for async tasks
- Redis shared with other services where possible
- No unnecessary middleware or apps installed

## Security

- Production SSL redirect enabled (except for `/ping/` and `/webhooks/`)
- Webhook signature validation using WhatsApp app secret
- API key authentication for all API endpoints
- CSRF exempt for webhook endpoints (external POST)
