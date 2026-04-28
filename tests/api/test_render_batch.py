"""Batch render endpoint tests — Phase 6."""

from __future__ import annotations

import fakeredis
import pytest
from fastapi.testclient import TestClient

from app.auth.clerk import ClerkPrincipal, current_user
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.services import billing, queue as queue_module


def _principal(uid: str) -> ClerkPrincipal:
    return ClerkPrincipal(user_id=uid, session_id="s", email=f"{uid}@x.com")


@pytest.fixture(autouse=True)
def fresh_schema_and_queue():
    Base.metadata.create_all(engine)
    queue_module.set_redis(fakeredis.FakeRedis(decode_responses=True))
    yield
    queue_module.set_redis(None)
    Base.metadata.drop_all(engine)


@pytest.fixture
def client():
    app.dependency_overrides[current_user] = lambda: _principal("alice")
    yield TestClient(app)
    app.dependency_overrides.pop(current_user, None)


def _make_project(client: TestClient) -> str:
    return client.post(
        "/api/projects",
        json={
            "template": "voiceover",
            "name": "test",
            "template_input": {
                "script": "Test script for batch render endpoint.",
                "background_color": "#0b0b0f",
                "caption_style": "bold_word",
                "aspect": "9:16",
            },
        },
    ).json()["id"]


def test_batch_render_returns_n_renders_and_charges_n_credits(client: TestClient):
    # Trigger the starter grant.
    starting = client.get("/api/billing").json()["balance"]
    pid = _make_project(client)

    res = client.post(
        f"/api/projects/{pid}/render-batch",
        json={"count": 3},
    )
    assert res.status_code == 202
    body = res.json()
    assert len(body) == 3
    # Each render has a unique job_id.
    job_ids = {r["job_id"] for r in body}
    assert len(job_ids) == 3

    # Charged 3 credits up-front.
    after = client.get("/api/billing").json()["balance"]
    assert after == starting - 3


def test_batch_render_returns_402_when_balance_too_low(client: TestClient):
    """Drain the balance to 1, then ask for a batch of 3 → 402."""
    client.get("/api/me")
    db = SessionLocal()
    try:
        from app.db.models import User
        user = db.query(User).filter(User.clerk_user_id == "alice").one()
        billing.get_balance(db, user.id)  # seeds the starter
        bal = billing.get_balance(db, user.id)
        if bal > 1:
            billing.consume_credits(db, user.id, bal - 1, "test_drain")
    finally:
        db.close()

    pid = _make_project(client)
    res = client.post(
        f"/api/projects/{pid}/render-batch",
        json={"count": 3},
    )
    assert res.status_code == 402


def test_batch_render_rejects_count_below_2_or_above_5(client: TestClient):
    pid = _make_project(client)
    assert client.post(
        f"/api/projects/{pid}/render-batch", json={"count": 1},
    ).status_code == 422
    assert client.post(
        f"/api/projects/{pid}/render-batch", json={"count": 6},
    ).status_code == 422


def test_batch_render_returns_404_for_other_users_project(client: TestClient):
    pid = _make_project(client)
    app.dependency_overrides[current_user] = lambda: _principal("bob")
    res = client.post(
        f"/api/projects/{pid}/render-batch",
        json={"count": 2},
    )
    assert res.status_code == 404
