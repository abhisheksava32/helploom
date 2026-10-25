# Production image for the ASGI web process and the Celery worker (same image,
# different command; see docker-compose.yml).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.11.16 /uv /uvx /bin/

WORKDIR /app

# Dependencies first so code changes do not invalidate this layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .

# collectstatic needs settings but no database; the key below exists only in this layer.
RUN SECRET_KEY=collectstatic-only DEBUG=false python manage.py collectstatic --noinput

RUN useradd --create-home --uid 1000 helploom \
    && mkdir -p /app/media \
    && chown -R helploom:helploom /app/media
USER helploom

EXPOSE 8000

CMD ["daphne", "--bind", "0.0.0.0", "--port", "8000", "--proxy-headers", "helploom.asgi:application"]
