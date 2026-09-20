import shutil

import redis
from fastapi import APIRouter, Depends

from app.analyzers.javascript_analyzer import _ESLINT_BIN
from app.core.redis_client import get_redis_client

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(redis_client: redis.Redis = Depends(get_redis_client)):
    try:
        redis_client.ping()
        redis_status = "available"
    except redis.RedisError:
        redis_status = "unavailable (caching and rate limiting degrade gracefully without it)"

    return {
        "status": "ok",
        "analyzers": {
            "cpp": "available" if shutil.which("cppcheck") else "unavailable (cppcheck not installed)",
            "python": "available",
            "javascript": "available" if (shutil.which("node") and _ESLINT_BIN.exists()) else "unavailable (run `npm install` in backend/tools/js-lint)",
            "java": "available" if shutil.which("javac") else "unavailable (JDK/javac not installed)",
        },
        "redis": redis_status,
    }

