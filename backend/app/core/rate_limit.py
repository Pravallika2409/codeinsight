"""
A small, transparent fixed-window rate limiter backed by Redis (INCR +
EXPIRE) rather than a third-party rate-limiting library -- for a project
this size, a custom ~30-line implementation is easier to audit than a new
dependency, and it doubles as a second concrete use of Redis alongside
caching (app/services/cache_service.py).

Like caching, this fails open: a Redis outage means requests simply aren't
rate-limited rather than being rejected, matching this project's general
policy of degrading optional infrastructure gracefully rather than letting
it take down a request.
"""
from __future__ import annotations

import logging
import time

import redis
from fastapi import Depends, HTTPException, Request, status

from app.core.config import Settings, get_settings
from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# Maps a rate-limit "bucket" name to the Settings attribute that holds its
# per-minute limit, read fresh on every call (not captured at import time)
# so tests can monkeypatch the settings object per-test, same pattern as
# MAX_CODE_SIZE_BYTES in tests/test_analyze_api.py.
_LIMIT_SETTINGS = {
    "analyze": "RATE_LIMIT_ANALYZE_PER_MINUTE",
    "login": "RATE_LIMIT_LOGIN_PER_MINUTE",
}


def rate_limit(bucket: str):
    """Returns a FastAPI dependency enforcing `bucket`'s per-minute limit,
    keyed by client IP. Call as `Depends(rate_limit("analyze"))`.
    """

    def _dependency(
        request: Request,
        redis_client: redis.Redis = Depends(get_redis_client),
        settings: Settings = Depends(get_settings),
    ) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return

        limit = getattr(settings, _LIMIT_SETTINGS[bucket])
        client_ip = request.client.host if request.client else "unknown"
        window = int(time.time() // 60)
        key = f"ratelimit:{bucket}:{client_ip}:{window}"

        try:
            count = redis_client.incr(key)
            if count == 1:
                redis_client.expire(key, 60)
        except redis.RedisError:
            logger.warning("Redis unavailable for rate limiting; request allowed through", exc_info=True)
            return

        if count > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: max {limit} requests per minute.",
            )

    return _dependency
