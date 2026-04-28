"""Render star/reject feedback tests (PR 12)."""

from __future__ import annotations

import fakeredis
import pytest
from fastapi.testclient import TestClient

from app.auth.clerk import ClerkPrincipal, current_user
from app.db.base import Base
from app.db.session import engine
from app.main import app
from app.services import queue as queue_module


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
    app.dependency_overrides[current_user] = lambda: _principal("user_alice")
    yield TestClient(app)
    app.dependency_overrides.pop(current_user, None)


def _new_render(client: TestClient) -> str:
    pid = client.post(
        "/api/projects",
        json={
            "template": "ai_story",
            "name": "test",
            "template_input": {
                "prompt": "Make a video about discipline at sunrise.",
                "duration": 15.0,
                "aspect": "9:16",
            },
        },
    ).json()["id"]
    rid = client.post(f"/api/projects/{pid}/render").json()["id"]
    return rid


def test_render_starts_with_no_decision(client: TestClient):
    rid = _new_render(client)
    res = client.get(f"/api/renders/{rid}")
    assert res.status_code == 200
    assert res.json()["starred"] is None


def test_star_then_reject_then_clear(client: TestClient):
    rid = _new_render(client)

    res = client.post(f"/api/renders/{rid}/star")
    assert res.status_code == 200
    assert res.json()["starred"] is True

    res = client.post(f"/api/renders/{rid}/reject")
    assert res.status_code == 200
    assert res.json()["starred"] is False

    res = client.delete(f"/api/renders/{rid}/feedback")
    assert res.status_code == 200
    assert res.json()["starred"] is None


def test_feedback_404_for_other_user(client: TestClient):
    rid = _new_render(client)

    app.dependency_overrides[current_user] = lambda: _principal("user_bob")
    res = client.post(f"/api/renders/{rid}/star")
    assert res.status_code == 404


def test_feedback_persists_in_get(client: TestClient):
    rid = _new_render(client)
    client.post(f"/api/renders/{rid}/star")
    res = client.get(f"/api/renders/{rid}")
    assert res.json()["starred"] is True
