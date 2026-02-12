FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install Python dependencies
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code
COPY . .

# Install the project itself
RUN uv sync --frozen --no-dev

# Collect static files (ignore errors if not configured)
RUN python manage.py collectstatic --noinput 2>/dev/null || true

EXPOSE 8080

CMD ["sh", "-c", "python manage.py migrate --noinput 2>/dev/null || true && gunicorn messaging_service.wsgi:application --bind 0.0.0.0:${PORT:-8080} --workers 2 --threads 2 --timeout 120 --max-requests 1000 --max-requests-jitter 50"]
