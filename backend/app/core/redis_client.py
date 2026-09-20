"""
Redis client accessor.

Mirrors app/database/session.py's get_db pattern: a real singleton client
in production, freely overridable in tests (see backend/tests/conftest.py,
which swaps this for a fakeredis instance so pytest never requires a
running Redis server).
"""
from __future__ import annotations

from functools import lru_cache

import redis

from app.core.config import get_settings


@lru_cache
def _build_client() -> redis.Redis:
    settings = get_settings()
    return redis.Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )


def get_redis_client() -> redis.Redis:
    """FastAPI dependency. A thin function (not the cached client itself)
    so `app.dependency_overrides[get_redis_client] = ...` works in tests.
    """
    return _build_client()
