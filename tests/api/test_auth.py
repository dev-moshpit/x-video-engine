"""Auth tests for the SaaS API (PR 2 + PR 3).

Five paths exercised:
  1. /api/me without an Authorization header → 401
  2. /api/me with an invalid bearer token → 401
  3. /api/me with the ``current_user`` dep overridden → 200 with the
     mirrored DB user record (lazy upsert)
  4. /api/me called twice with the same principal → idempotent (no
     duplicate user row)
  5. /health remains public

env vars + sys.path are set in tests/api/conftest.py.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.clerk import ClerkPrincipal, current_user
from app.db.base import Base
from app.db.models import User
from app.db.session import SessionLocal, engine
from app.main import app


@pytest.fixture(autouse=True)
def fresh_schema():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def authed_client():
    fake = ClerkPrincipal(
        user_id="user_test123",
        session_id="sess_test",
        email="dev@example.com",
    )
    app.dependency_overrides[current_user] = lambda: fake
    yield TestClient(app)
    app.dependency_overrides.pop(current_user, None)


def test_me_without_token_returns_401(client: TestClient):
    res = client.get("/api/me")
    assert res.status_code == 401
    assert res.headers.get("WWW-Authenticate") == "Bearer"


def test_me_with_malformed_token_returns_401(client: TestClient):
    res = client.get(
        "/api/me", headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert res.status_code == 401


def test_me_returns_mirrored_db_user(authed_client: TestClient):
    res = authed_client.get(
        "/api/me", headers={"Authorization": "Bearer mock"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["user_id"] == "user_test123"
    assert body["email"] == "dev@example.com"
    assert body["tier"] == "free"
    assert "db_user_id" in body
    assert "created_at" in body

    # The row was actually written.
    db = SessionLocal()
    try:
        row = db.execute(
            select(User).where(User.clerk_user_id == "user_test123")
        ).scalar_one_or_none()
    finally:
        db.close()
    assert row is not None
    assert str(row.id) == body["db_user_id"]


def test_me_is_idempotent(authed_client: TestClient):
    headers = {"Authorization": "Bearer mock"}
    first = authed_client.get("/api/me", headers=headers).json()
    second = authed_client.get("/api/me", headers=headers).json()

    # Same DB user row both calls — no duplicate insert.
    assert first["db_user_id"] == second["db_user_id"]

    db = SessionLocal()
    try:
        rows = db.execute(
            select(User).where(User.clerk_user_id == "user_test123")
        ).scalars().all()
    finally:
        db.close()
    assert len(rows) == 1


def test_health_remains_public(client: TestClient):
    res = client.get("/health")
    assert res.status_code == 200
