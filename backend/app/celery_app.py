"""
Celery application instance.

Used for background processing of /api/analyze requests submitted via
POST /api/analyze/async (see app/tasks/analysis_tasks.py and
app/api/tasks.py) -- useful when a caller doesn't want to block on
cppcheck/javac/ESLint subprocess calls plus an optional AI network call.
Synchronous POST /api/analyze is unaffected and remains the default way to
use the API.
"""
from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "codeinsight_ai",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.analysis_tasks", "app.tasks.github_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    # Results aren't meant to be retrieved forever -- avoid growing Redis
    # unboundedly with stale task results.
    result_expires=3600,
)
