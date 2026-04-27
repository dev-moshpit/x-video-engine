"""Render endpoint tests (PR 6) — fakeredis as the queue."""

from __future__ import annotations

import json

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
    fake = fakeredis.FakeRedis(decode_responses=True)
    queue_module.set_redis(fake)
    yield fake
    queue_module.set_redis(None)
    Base.metadata.drop_all(engine)


@pytest.fixture
def client():
    app.dependency_overrides[current_user] = lambda: _principal("user_alice")
    yield TestClient(app)
    app.dependency_overrides.pop(current_user, None)


def _create_project(client: TestClient) -> str:
    res = client.post(
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
    )
    return res.json()["id"]


def test_create_render_enqueues_and_returns_pending(
    client: TestClient, fresh_schema_and_queue: fakeredis.FakeRedis,
):
    pid = _create_project(client)
    res = client.post(f"/api/projects/{pid}/render")
    assert res.status_code == 202
    body = res.json()
    assert body["stage"] == "pending"
    assert body["progress"] == 0.0
    assert body["job_id"]

    # Job is on the queue.
    raw = fresh_schema_and_queue.lpop("saas:render:jobs")
    assert raw is not None
    payload = json.loads(raw)
    assert payload["job_id"] == body["job_id"]
    assert payload["template"] == "ai_story"
    assert payload["template_input"]["prompt"].startswith("Make a video")


def test_get_render_by_id(client: TestClient):
    pid = _create_project(client)
    render = client.post(f"/api/projects/{pid}/render").json()
    rid = render["id"]

    res = client.get(f"/api/renders/{rid}")
    assert res.status_code == 200
    assert res.json()["job_id"] == render["job_id"]


def test_get_render_404_for_other_user(client: TestClient):
    pid = _create_project(client)
    rid = client.post(f"/api/projects/{pid}/render").json()["id"]

    # Switch to another user
    app.dependency_overrides[current_user] = lambda: _principal("user_bob")
    res = client.get(f"/api/renders/{rid}")
    assert res.status_code == 404


def test_render_create_404_for_unknown_project(client: TestClient):
    import uuid as _uuid
    res = client.post(f"/api/projects/{_uuid.uuid4()}/render")
    assert res.status_code == 404
