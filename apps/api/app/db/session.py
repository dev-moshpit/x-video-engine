"""Database engine, session factory, and FastAPI dependency.

DATABASE_URL is read once at module import. Defaults to the local
docker-compose Postgres so ``pnpm dev:api`` works after ``pnpm
dev:infra``. Tests set ``DATABASE_URL=sqlite:///:memory:`` (with a
StaticPool so the in-memory DB is shared across requests).
"""

from __future__ import annotations

import os
from typing import Annotated, Iterator

from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://saas:saas@localhost:5432/saas",
)


def _engine_kwargs(url: str) -> dict:
    """Per-dialect engine kwargs.

    For sqlite we pin a single shared connection (``StaticPool``) so the
    in-memory db survives across the multiple connections FastAPI's
    TestClient + endpoint deps would otherwise open.
    """
    if url.startswith("sqlite"):
        from sqlalchemy.pool import StaticPool
        return {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        }
    return {}


engine = create_engine(DATABASE_URL, future=True, **_engine_kwargs(DATABASE_URL))

SessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, future=True,
)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]
