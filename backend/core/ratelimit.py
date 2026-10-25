"""Fixed window rate limiting on the Django cache.

DRF throttles cover HTTP; websockets need the same protection per IP, so consumers
call these helpers directly. With Redis configured the counters are shared by every
server process; with the local memory cache they are per process, which is enough
for development.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after: int


def _window(window_seconds: int) -> tuple[int, int]:
    now = int(time.time())
    start = now - (now % window_seconds)
    return start, start + window_seconds - now


def hit(key: str, limit: int, window_seconds: int = 60) -> RateLimitResult:
    start, retry_after = _window(window_seconds)
    cache_key = f"rl:{key}:{start}"
    cache.add(cache_key, 0, timeout=window_seconds + 1)
    try:
        count = cache.incr(cache_key)
    except ValueError:  # expired between add and incr
        cache.set(cache_key, 1, timeout=window_seconds + 1)
        count = 1
    return RateLimitResult(allowed=count <= limit, remaining=max(limit - count, 0), retry_after=retry_after)


async def ahit(key: str, limit: int, window_seconds: int = 60) -> RateLimitResult:
    start, retry_after = _window(window_seconds)
    cache_key = f"rl:{key}:{start}"
    await cache.aadd(cache_key, 0, timeout=window_seconds + 1)
    try:
        count = await cache.aincr(cache_key)
    except ValueError:
        await cache.aset(cache_key, 1, timeout=window_seconds + 1)
        count = 1
    return RateLimitResult(allowed=count <= limit, remaining=max(limit - count, 0), retry_after=retry_after)


def client_ip_from_headers(remote_addr: str | None, forwarded_for: str | None) -> str:
    """Pick the client IP, trusting only as many X-Forwarded-For hops as we have proxies."""
    proxies = settings.TRUSTED_PROXY_COUNT
    if proxies > 0 and forwarded_for:
        hops = [part.strip() for part in forwarded_for.split(",") if part.strip()]
        if len(hops) >= proxies:
            return hops[-proxies]
    return remote_addr or "unknown"


def scope_client_ip(scope: dict) -> str:
    client = scope.get("client") or (None, None)
    forwarded = None
    for name, value in scope.get("headers", []):
        if name == b"x-forwarded-for":
            forwarded = value.decode("latin-1")
            break
    return client_ip_from_headers(client[0], forwarded)


def hash_ip(ip: str) -> str:
    """Keyed hash so we can count and rate limit visitors without storing raw IPs."""
    digest = hmac.new(settings.SECRET_KEY.encode(), ip.encode(), hashlib.sha256)
    return digest.hexdigest()[:32]
