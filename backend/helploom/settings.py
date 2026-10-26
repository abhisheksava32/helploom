"""Helploom settings: one module, configured entirely from the environment.

backend/.env is loaded first (real environment variables win over it), so the same
code runs on a laptop, in CI and in containers. DEBUG switches the development
conveniences on; when it is off the production hardening below applies and the app
refuses to boot with an unsafe SECRET_KEY. Every variable is documented in
backend/.env.example.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env", override=False)

HELPLOOM_VERSION = "0.1.0"


def env_str(name: str, default: str = "") -> str:
    # An empty value means "not set", so a blank line copied from .env.example keeps
    # the default instead of overriding it with "".
    return os.environ.get(name, "").strip() or default


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ImproperlyConfigured(f"{name} must be true or false, got {raw!r}")


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} must be an integer, got {raw!r}") from exc


def env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} must be a number, got {raw!r}") from exc


def env_optional_float(name: str) -> float | None:
    raw = os.environ.get(name, "").strip()
    return env_float(name, 0.0) if raw else None


def env_list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def env_choice(name: str, default: str, choices: set[str]) -> str:
    value = env_str(name, default).lower()
    if value not in choices:
        allowed = ", ".join(sorted(choices))
        raise ImproperlyConfigured(f"{name} must be one of: {allowed}; got {value!r}")
    return value


# Environment

DEBUG = env_bool("DEBUG", False)
# pytest is imported before settings load, so this is reliable without extra config.
# Tests force offline, deterministic providers below whatever .env says.
TESTING = env_bool("TESTING", "pytest" in sys.modules)

_INSECURE_KEY_PREFIX = "insecure-"
SECRET_KEY = env_str("SECRET_KEY", "")
if not SECRET_KEY:
    if not (DEBUG or TESTING):
        raise ImproperlyConfigured("Set SECRET_KEY to a long random value when DEBUG is off.")
    SECRET_KEY = f"{_INSECURE_KEY_PREFIX}local-development-key"
if SECRET_KEY.startswith(_INSECURE_KEY_PREFIX) and not (DEBUG or TESTING):
    raise ImproperlyConfigured("The development SECRET_KEY cannot be used when DEBUG is off.")

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", ["localhost", "127.0.0.1", "[::1]"])

FRONTEND_URL = env_str("FRONTEND_URL", "http://localhost:3000").rstrip("/")
BACKEND_URL = env_str("BACKEND_URL", "http://localhost:8000").rstrip("/")
# Websocket base the widget embed snippet points at; differs from BACKEND_URL behind a proxy.
PUBLIC_WS_URL = env_str("PUBLIC_WS_URL", "ws://localhost:8000").rstrip("/")

# Applications

INSTALLED_APPS = [
    # daphne first so runserver serves the ASGI application, websockets included.
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "channels",
    "core",
    "accounts",
    "knowledge",
    "assistant",
    "widget",
    "billing",
    "analytics",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Serves the admin's collected static files in production; runserver does it in DEBUG.
    *([] if DEBUG or TESTING else ["whitenoise.middleware.WhiteNoiseMiddleware"]),
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "helploom.urls"
WSGI_APPLICATION = "helploom.wsgi.application"
ASGI_APPLICATION = "helploom.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# Database: PostgreSQL everywhere, so pgvector and full-text search behave the same in
# tests and production. pytest-django creates test_<name> and the first knowledge
# migration installs the vector extension there.

DATABASE_URL = env_str("DATABASE_URL", "postgres://localhost:5432/helploom")
DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        # Persistent connections do not mix well with ASGI thread hopping; pool with
        # PgBouncer in production instead.
        conn_max_age=env_int("DB_CONN_MAX_AGE", 0),
        conn_health_checks=True,
    )
}
if not DATABASES["default"]["ENGINE"].endswith("postgresql"):
    raise ImproperlyConfigured("DATABASE_URL must point at PostgreSQL (postgres://...).")
_test_db_name = env_str("DATABASE_TEST_NAME", "")
if _test_db_name:
    DATABASES["default"]["TEST"] = {"NAME": _test_db_name}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files and media

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Uploaded documents are tenant private: MEDIA_URL is never routed. Members read
# extracted text through the knowledge API instead.
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(env_str("MEDIA_ROOT", str(BASE_DIR / "media")))
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG or TESTING
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

# Uploads

MAX_UPLOAD_MB = env_int("MAX_UPLOAD_MB", 20)
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
MAX_FILES_PER_UPLOAD = env_int("MAX_FILES_PER_UPLOAD", 10)
DATA_UPLOAD_MAX_NUMBER_FILES = MAX_FILES_PER_UPLOAD
# Larger files spill to a temp file instead of memory while the request is parsed.
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
# Extension to canonical MIME type. The upload validator sniffs the bytes and only
# trusts the extension after the content agrees with it.
ALLOWED_DOCUMENT_TYPES: dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "md": "text/markdown",
    "markdown": "text/markdown",
    "txt": "text/plain",
    "html": "text/html",
    "htm": "text/html",
}

# REST API

THROTTLE_RATES: dict[str, str] = {
    "anon": env_str("THROTTLE_ANON", "60/min"),
    "user": env_str("THROTTLE_USER", "600/min"),
    # Views opt in with throttle_scope = "auth" | "refresh" | "upload" | "webhook" | "widget".
    "auth": env_str("THROTTLE_AUTH", "10/min"),
    # Every page load restores the session once, so refresh gets its own, wider budget.
    "refresh": env_str("THROTTLE_REFRESH", "60/min"),
    "upload": env_str("THROTTLE_UPLOAD", "30/min"),
    "webhook": env_str("THROTTLE_WEBHOOK", "120/min"),
    "widget": env_str("THROTTLE_WIDGET", "120/min"),
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        *(["rest_framework.renderers.BrowsableAPIRenderer"] if DEBUG else []),
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ],
    "DEFAULT_PAGINATION_CLASS": "core.pagination.StandardPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": THROTTLE_RATES,
    # Without this DRF trusts the whole X-Forwarded-For header, so any client could
    # pick its own IP and step around the per IP throttles. Set after the proxy
    # settings below are read.
    "NUM_PROXIES": None,
    "EXCEPTION_HANDLER": "core.exceptions.exception_handler",
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env_int("JWT_ACCESS_MINUTES", 15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env_int("JWT_REFRESH_DAYS", 14)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "SIGNING_KEY": env_str("JWT_SIGNING_KEY", "") or SECRET_KEY,
}

# The refresh token lives in an httpOnly cookie so page scripts never see it; the
# access token stays in memory on the client. Same site (localhost:3000 and :8000, or
# app. and api. subdomains), so SameSite=Lax is enough.
REFRESH_COOKIE_NAME = "helploom_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth/"
REFRESH_COOKIE_DOMAIN = env_str("REFRESH_COOKIE_DOMAIN", "") or None
REFRESH_COOKIE_SECURE = env_bool("REFRESH_COOKIE_SECURE", not DEBUG)
REFRESH_COOKIE_SAMESITE = "Lax"
# A just rotated refresh token is accepted again for this long, so a reload that cancels
# the refresh request mid flight does not sign the user out. 0 makes tokens strictly
# single use.
REFRESH_REUSE_GRACE_SECONDS = env_int("REFRESH_REUSE_GRACE_SECONDS", 30)
# Cookie authenticated endpoints require this header. Browsers cannot attach a custom
# header cross origin without a CORS preflight, which only the dashboard passes.
CSRF_GUARD_HEADER = "X-Requested-With"

# Dashboard requests name their workspace in this header (docs/API.md, "Tenancy").
ORGANIZATION_HEADER = "X-Organization-Id"

# CORS and CSRF: only the dashboard calls the REST API with credentials. The widget's
# public config endpoint adds each organisation's allowed origins dynamically, and the
# widget socket checks them itself.

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", [FRONTEND_URL])
CORS_ALLOW_CREDENTIALS = True
CORS_URLS_REGEX = r"^/api/.*$"
CORS_ALLOW_HEADERS = (
    "accept",
    "authorization",
    "content-type",
    "origin",
    "x-organization-id",
    "x-requested-with",
)
CORS_EXPOSE_HEADERS = ("retry-after",)
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", [FRONTEND_URL])

# Real time and caching. Without Redis everything stays in process, which is all a
# single local server needs.

REDIS_URL = env_str("REDIS_URL", "")
if REDIS_URL and not TESTING:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [REDIS_URL]},
        }
    }
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
            "KEY_PREFIX": "helploom",
        }
    }
else:
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "helploom",
        }
    }

WEBSOCKET_AUTH_TIMEOUT_SECONDS = env_int("WEBSOCKET_AUTH_TIMEOUT_SECONDS", 10)
# Number of reverse proxies in front of the app whose X-Forwarded-For entries we trust.
# Shared by DRF throttles and the websocket rate limits (core.ratelimit).
TRUSTED_PROXY_COUNT = env_int("TRUSTED_PROXY_COUNT", 0)
REST_FRAMEWORK["NUM_PROXIES"] = TRUSTED_PROXY_COUNT

# Background work. Celery runs only when a broker is configured; otherwise jobs go to an
# in-process thread pool, which keeps the local setup to PostgreSQL, uv and Node.

CELERY_BROKER_URL = env_str("CELERY_BROKER_URL", "")
CELERY_RESULT_BACKEND = env_str("CELERY_RESULT_BACKEND", "") or None
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = env_int("CELERY_TASK_TIME_LIMIT", 900)
CELERY_TASK_SOFT_TIME_LIMIT = env_int("CELERY_TASK_SOFT_TIME_LIMIT", 840)
CELERY_TASK_DEFAULT_QUEUE = "helploom"
# Run background jobs inline, in the calling thread. Tests turn this on.
BACKGROUND_TASKS_EAGER = env_bool("BACKGROUND_TASKS_EAGER", False)
INGESTION_MAX_WORKERS = env_int("INGESTION_MAX_WORKERS", 2)

# Language model providers

LLM_PROVIDER = env_choice("LLM_PROVIDER", "auto", {"auto", "ollama", "claude", "extractive"})

OLLAMA_URL = env_str("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = env_str("OLLAMA_MODEL", "llama3.2")
OLLAMA_EMBED_MODEL = env_str("OLLAMA_EMBED_MODEL", "nomic-embed-text")
OLLAMA_CONNECT_TIMEOUT_SECONDS = env_float("OLLAMA_CONNECT_TIMEOUT_SECONDS", 2.0)
OLLAMA_TIMEOUT_SECONDS = env_float("OLLAMA_TIMEOUT_SECONDS", 120.0)
OLLAMA_KEEP_ALIVE = env_str("OLLAMA_KEEP_ALIVE", "10m")
# How long a reachability probe result is reused before asking Ollama again.
PROVIDER_PROBE_TTL_SECONDS = env_int("PROVIDER_PROBE_TTL_SECONDS", 30)

# Read only from the environment and only to report whether Claude is configured. The
# SDK client reads ANTHROPIC_API_KEY itself; the key is never logged or returned.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = env_str("CLAUDE_MODEL", "claude-opus-5-5")
CLAUDE_FALLBACK_MODEL = env_str("CLAUDE_FALLBACK_MODEL", "claude-opus-4-8")
CLAUDE_FALLBACK_BETA = "server-side-fallback-2026-06-01"
CLAUDE_MAX_TOKENS = env_int("CLAUDE_MAX_TOKENS", 4096)
# The chat route runs at low effort to keep time to first token down. The variable is
# CLAUDE_CHAT_EFFORT, not CLAUDE_EFFORT, because developer tools export the latter and a
# shell value would silently win over backend/.env.
CLAUDE_EFFORT = env_choice("CLAUDE_CHAT_EFFORT", "low", {"low", "medium", "high", "xhigh", "max"})
CLAUDE_TIMEOUT_SECONDS = env_float("CLAUDE_TIMEOUT_SECONDS", 60.0)

# USD per million tokens, used for the cost report. Local providers cost nothing.
# cache_write is the 5 minute ephemeral cache price (1.25x input).
LLM_PRICING_PER_MTOK: dict[str, dict[str, str]] = {
    "claude-opus-5-5": {"input": "4.00", "output": "20.00", "cache_read": "0.20", "cache_write": "5.00"},
    "claude-opus-4-8": {"input": "5.00", "output": "25.00", "cache_read": "0.50", "cache_write": "6.25"},
}

# Embeddings and retrieval

EMBEDDER = env_choice("EMBEDDER", "auto", {"auto", "ollama", "hashing"})
# Fixed by the knowledge migrations: both embedders produce vectors of this size.
EMBEDDING_DIMENSIONS = 768
EMBEDDING_BATCH_SIZE = env_int("EMBEDDING_BATCH_SIZE", 32)

CHUNK_TARGET_TOKENS = env_int("CHUNK_TARGET_TOKENS", 350)
CHUNK_OVERLAP_TOKENS = env_int("CHUNK_OVERLAP_TOKENS", 50)

RETRIEVAL_TOP_K = env_int("RETRIEVAL_TOP_K", 5)
# Candidates pulled from each side (vector and keyword) before fusion.
RETRIEVAL_CANDIDATES = env_int("RETRIEVAL_CANDIDATES", 24)
RRF_K = env_int("RRF_K", 60)
RETRIEVAL_MMR = env_bool("RETRIEVAL_MMR", True)
RETRIEVAL_MMR_LAMBDA = env_float("RETRIEVAL_MMR_LAMBDA", 0.7)
HNSW_EF_SEARCH = env_int("HNSW_EF_SEARCH", 80)
# Minimum cosine similarity of the best retrieved passage before we attempt an answer.
# Below it the assistant says it could not find the answer and offers a human. Score
# scales differ per embedder, so None means "use the active embedder's default", which
# the eval harness calibrates; set a number to override it for every embedder.
RELEVANCE_THRESHOLD = env_optional_float("RELEVANCE_THRESHOLD")

# Assistant behaviour

ASSISTANT_HISTORY_TURNS = env_int("ASSISTANT_HISTORY_TURNS", 6)
ASSISTANT_MAX_QUESTION_CHARS = env_int("ASSISTANT_MAX_QUESTION_CHARS", 2000)
ASSISTANT_EXTRACTIVE_MAX_SENTENCES = env_int("ASSISTANT_EXTRACTIVE_MAX_SENTENCES", 4)

# Widget

WIDGET_MESSAGES_PER_MINUTE = env_int("WIDGET_MESSAGES_PER_MINUTE", 20)
WIDGET_CONNECTIONS_PER_MINUTE = env_int("WIDGET_CONNECTIONS_PER_MINUTE", 30)
# Lets http://localhost:* embed any widget while DEBUG is on, for local testing.
WIDGET_ALLOW_LOCALHOST_IN_DEBUG = env_bool("WIDGET_ALLOW_LOCALHOST_IN_DEBUG", True)

# Billing. Without a Stripe key the product runs in a clearly labelled demo mode that
# switches plans instantly.

STRIPE_SECRET_KEY = env_str("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = env_str("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_STARTER = env_str("STRIPE_PRICE_STARTER", "")
STRIPE_PRICE_PRO = env_str("STRIPE_PRICE_PRO", "")

# Accounts and email

INVITATION_EXPIRY_DAYS = env_int("INVITATION_EXPIRY_DAYS", 7)
EMAIL_BACKEND = env_str("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env_str("EMAIL_HOST", "localhost")
EMAIL_PORT = env_int("EMAIL_PORT", 25)
EMAIL_HOST_USER = env_str("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env_str("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", False)
DEFAULT_FROM_EMAIL = env_str("DEFAULT_FROM_EMAIL", "Helploom <no-reply@helploom.local>")

# Tests never depend on a running Ollama, a Claude key, Stripe, Redis or SMTP, whatever
# the developer's .env contains.

if TESTING:
    LLM_PROVIDER = "extractive"
    EMBEDDER = "hashing"
    CLAUDE_EFFORT = "low"
    ANTHROPIC_API_KEY = ""
    STRIPE_SECRET_KEY = ""
    STRIPE_WEBHOOK_SECRET = ""
    CELERY_BROKER_URL = ""
    BACKGROUND_TASKS_EAGER = True
    EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    MEDIA_ROOT = Path(tempfile.gettempdir()) / "helploom-test-media"
    REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = dict.fromkeys(THROTTLE_RATES, "10000/min")

BILLING_MODE = "stripe" if STRIPE_SECRET_KEY else "demo"

# Production hardening. Each switch can be overridden for unusual deployments, for
# example SECURE_SSL_REDIRECT=false when TLS ends at a proxy that already redirects.

_harden = not DEBUG and not TESTING
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if _harden else None
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", _harden)
SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 60 * 60 * 24 * 30 if _harden else 0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = _harden
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SESSION_COOKIE_SECURE = _harden
CSRF_COOKIE_SECURE = _harden
X_FRAME_OPTIONS = "DENY"
# Health checks arrive over plain HTTP from inside the network.
SECURE_REDIRECT_EXEMPT = [r"^api/v1/health/$"]

# Logging

LOG_LEVEL = env_str("LOG_LEVEL", "INFO").upper()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        # Own handler and no propagation, so runserver lines are not printed twice.
        "django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "django.channels.server": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "django.db.backends": {"level": "WARNING"},
        "httpx": {"level": "WARNING"},
        "httpcore": {"level": "WARNING"},
        "daphne": {"level": "WARNING"},
    },
}
