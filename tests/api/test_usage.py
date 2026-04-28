"""Usage endpoint tests (PR 11)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.auth.clerk import ClerkPrincipal, current_user
from app.db.base import Base
from app.db.models import Usage, User
from app.db.session import SessionLocal, engine
from app.main import app


def _principal(uid: str) -> ClerkPrincipal:
    return ClerkPrincipal(user_id=uid, session_id="s", email=f"{uid}@x.com")


@pytest.fixture(autouse=True)
def fresh_schema():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client():
    app.dependency_overrides[current_user] = lambda: _principal("user_alice")
    yield TestClient(app)
    app.dependency_overrides.pop(current_user, None)


def _seed_usage(user_id: uuid.UUID):
    db = SessionLocal()
    try:
        db.add(Usage(user_id=user_id, kind="render_seconds", value=12.5))
        db.add(Usage(user_id=user_id, kind="render_seconds", value=7.5))
        db.add(Usage(user_id=user_id, kind="exports", value=1))
        db.add(Usage(user_id=user_id, kind="exports", value=1))
        db.commit()
    finally:
        db.close()


def test_usage_returns_zero_for_new_user(client: TestClient):
    res = client.get("/api/usage")
    assert res.status_code == 200
    body = res.json()
    assert body == {"render_seconds": 0.0, "exports": 0.0}


def test_usage_aggregates_kinds(client: TestClient):
    # /api/me triggers the lazy upsert so a User row exists.
    me = client.get("/api/me").json()
    user_id = uuid.UUID(me["db_user_id"])

    _seed_usage(user_id)

    res = client.get("/api/usage")
    assert res.status_code == 200
    body = res.json()
    assert body["render_seconds"] == 20.0
    assert body["exports"] == 2.0


def test_usage_is_user_scoped(client: TestClient):
    # Alice's usage shouldn't show up under Bob's account.
    me = client.get("/api/me").json()
    alice_id = uuid.UUID(me["db_user_id"])
    _seed_usage(alice_id)

    app.dependency_overrides[current_user] = lambda: _principal("user_bob")
    res = client.get("/api/usage")
    body = res.json()
    assert body["render_seconds"] == 0.0
    assert body["exports"] == 0.0


def test_usage_requires_auth():
    bare = TestClient(app)
    res = bare.get("/api/usage")
    assert res.status_code == 401
