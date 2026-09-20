"""
SQLAlchemy engine/session setup.

DATABASE_URL is read from settings (env-configurable, see .env.example).
Local dev and Docker Compose (Phase 5) point this at PostgreSQL; the test
suite overrides `get_db` to point at an isolated SQLite database instead,
so `pytest` never requires a running Postgres server (see tests/conftest.py).
This project was developed and manually verified against a real local
PostgreSQL 16 instance -- SQLite is a test-only convenience, not the
intended production database.
"""
from __future__ import annotations

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

_connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Declarative base every ORM model inherits from."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a request-scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
