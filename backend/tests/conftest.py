"""
Shared pytest fixtures.

Tests run against an isolated in-memory SQLite database (via StaticPool, so
all connections in a test share the same in-memory DB) rather than
PostgreSQL, so `pytest` never requires a running Postgres server. This
project was manually verified end-to-end against a real local PostgreSQL 16
instance during development (see README) -- SQLite here is purely a
test-hermeticity choice, not a claim that the app runs on SQLite in
production (Alembic's migrations, for instance, are only maintained against
the Postgres dialect).

Similarly, Redis-backed caching/rate-limiting (Phase 5) run against a fresh
`fakeredis` instance per test rather than a real Redis server, and Celery
(also Phase 5) runs in eager mode (tasks execute synchronously, in-process,
with no broker/worker needed) with an in-memory result backend. Both were
manually verified against real Redis and a real Celery worker during
development (see README).
"""
import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.database.session as db_session_module
import app.models as models  # noqa: F401 - populates Base.metadata
from app.celery_app import celery_app
from app.core.redis_client import get_redis_client
from app.database.session import Base, get_db
from app.main import app

_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)

# The Celery task (app/tasks/analysis_tasks.py) imports SessionLocal *inside*
# its function body specifically so this module-level monkeypatch is picked
# up -- a top-level `from app.database.session import SessionLocal` in the
# task module would bind the name once at import time and never see this
# override.
db_session_module.SessionLocal = _TestSessionLocal

# Tasks run synchronously in-process; no broker or worker needed for tests.
celery_app.conf.task_always_eager = True
celery_app.conf.task_eager_propagates = True
celery_app.conf.task_store_eager_result = True
celery_app.conf.result_backend = "cache+memory://"


def _override_get_db():
    db = _TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture(autouse=True)
def _fresh_database():
    """Every test gets a clean schema -- no cross-test data leakage."""
    Base.metadata.create_all(bind=_engine)
    yield
    Base.metadata.drop_all(bind=_engine)


@pytest.fixture(autouse=True)
def _fresh_redis():
    """Every test gets its own in-memory fake Redis -- no cross-test cache
    hits or rate-limit counters bleeding between tests.
    """
    fake = fakeredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis_client] = lambda: fake
    yield fake
    fake.flushall()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers(client):
    """Registers and logs in a fresh user, returning ready-to-use auth headers."""

    def _make(email: str = "dev@example.com", password: str = "correct-horse-battery"):
        client.post("/api/auth/register", json={"email": email, "password": password})
        resp = client.post("/api/auth/login", json={"email": email, "password": password})
        token = resp.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return _make
