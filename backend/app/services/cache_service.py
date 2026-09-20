"""
Caches POST /api/analyze results in Redis, keyed by an exact hash of the
inputs that affect the result (language, filename, code, and whether AI
review was requested). Purely a performance optimization: `cppcheck`,
`javac`, ESLint, and especially the AI call are all real subprocess/network
calls, and identical resubmissions (a very common pattern -- re-running the
same snippet, a frontend double-submit, a demo re-run) shouldn't pay that
cost twice within the TTL window.

Like every other optional infrastructure dependency in this project
(cppcheck/ESLint/javac being absent, no AI key configured), a Redis outage
degrades to "skip the optimization," never a failed request -- every
function here fails open to a cache miss on any Redis error.
"""
from __future__ import annotations

import hashlib
import logging

import redis

from app.core.config import Settings
from app.schemas.analysis import AnalyzeRequest, AnalyzeResponse

logger = logging.getLogger(__name__)


def build_cache_key(request: AnalyzeRequest) -> str:
    raw = f"{request.language.value}:{request.filename}:{request.include_ai_review}:{request.code}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"analysis-cache:{digest}"


def get_cached_response(client: redis.Redis, cache_key: str) -> AnalyzeResponse | None:
    try:
        raw = client.get(cache_key)
    except redis.RedisError:
        logger.warning("Redis unavailable for cache read; proceeding without cache", exc_info=True)
        return None
    if raw is None:
        return None
    try:
        return AnalyzeResponse.model_validate_json(raw)
    except ValueError:
        # Defensive: a schema change made an old cached entry unparsable.
        # Treat it as a miss rather than failing the request.
        logger.warning("Cached analysis response failed to validate; treating as a cache miss")
        return None


def set_cached_response(client: redis.Redis, cache_key: str, response: AnalyzeResponse, settings: Settings) -> None:
    try:
        # analysis_id is per-request/persistence-specific, never part of
        # what should be reused from cache.
        cache_copy = response.model_copy(update={"analysis_id": None})
        client.setex(cache_key, settings.ANALYSIS_CACHE_TTL_SECONDS, cache_copy.model_dump_json())
    except redis.RedisError:
        logger.warning("Redis unavailable for cache write; result was not cached", exc_info=True)
