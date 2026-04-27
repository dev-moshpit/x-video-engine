"""Project CRUD tests (PR 4)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth.clerk import ClerkPrincipal, current_user
from app.db.base import Base
from app.db.session import engine
from app.main import app


def _principal(uid: str, email: str = "x@example.com") -> ClerkPrincipal:
    return ClerkPrincipal(user_id=uid, session_id="sess_x", email=email)


@pytest.fixture(autouse=True)
def fresh_schema():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def acting_as():
    """Factory: switch the current_user dep override mid-test.

    Returns a callable ``acting_as(user_id, email=None) -> TestClient``.
    Cleans the override on teardown. Using a factory (vs. multiple
    fixtures) avoids the issue where two fixtures both set the same
    dep override and the second silently wins.
    """
    def _set(uid: str, email: str = None) -> TestClient:
        app.dependency_overrides[current_user] = (
            lambda: _principal(uid, email or f"{uid}@example.com")
        )
        return TestClient(app)
    yield _set
    app.dependency_overrides.pop(current_user, None)


VALID_AI_STORY_INPUT = {
    "prompt": "Make a motivational video about discipline.",
    "duration": 20.0,
    "aspect": "9:16",
}


def test_create_lists_get_lifecycle(acting_as):
    client = acting_as("user_alice")
    res = client.post(
        "/api/projects",
        json={
            "template": "ai_story",
            "name": "First short",
            "template_input": VALID_AI_STORY_INPUT,
        },
    )
    assert res.status_code == 201
    project_id = res.json()["id"]

    res = client.get("/api/projects")
    assert res.status_code == 200
    assert len(res.json()) == 1
    assert res.json()[0]["name"] == "First short"

    res = client.get(f"/api/projects/{project_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["template"] == "ai_story"
    assert body["template_input"]["prompt"] == VALID_AI_STORY_INPUT["prompt"]
    assert body["renders"] == []


def test_unknown_template_rejected(acting_as):
    client = acting_as("user_alice")
    res = client.post(
        "/api/projects",
        json={
            "template": "fake_text",   # Phase 2 — not in registry yet
            "name": "Should fail",
            "template_input": {},
        },
    )
    assert res.status_code == 422


def test_invalid_template_input_rejected(acting_as):
    client = acting_as("user_alice")
    res = client.post(
        "/api/projects",
        json={
            "template": "ai_story",
            "name": "Should fail",
            "template_input": {"prompt": "hi"},  # too short, < 10 chars
        },
    )
    assert res.status_code == 422


def test_patch_updates_name_and_input(acting_as):
    client = acting_as("user_alice")
    pid = client.post(
        "/api/projects",
        json={
            "template": "ai_story",
            "name": "v1",
            "template_input": VALID_AI_STORY_INPUT,
        },
    ).json()["id"]

    res = client.patch(
        f"/api/projects/{pid}",
        json={
            "name": "v2",
            "template_input": {**VALID_AI_STORY_INPUT, "duration": 30.0},
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "v2"
    assert body["template_input"]["duration"] == 30.0


def test_delete_removes_project(acting_as):
    client = acting_as("user_alice")
    pid = client.post(
        "/api/projects",
        json={
            "template": "ai_story",
            "name": "v1",
            "template_input": VALID_AI_STORY_INPUT,
        },
    ).json()["id"]

    res = client.delete(f"/api/projects/{pid}")
    assert res.status_code == 204

    res = client.get(f"/api/projects/{pid}")
    assert res.status_code == 404


def test_cannot_read_another_users_project(acting_as):
    # Alice creates
    alice = acting_as("user_alice")
    pid = alice.post(
        "/api/projects",
        json={
            "template": "ai_story",
            "name": "alice's secret",
            "template_input": VALID_AI_STORY_INPUT,
        },
    ).json()["id"]

    # Bob attempts read / write / delete on Alice's project
    bob = acting_as("user_bob")
    assert bob.get(f"/api/projects/{pid}").status_code == 404
    assert bob.patch(
        f"/api/projects/{pid}", json={"name": "stolen"},
    ).status_code == 404
    assert bob.delete(f"/api/projects/{pid}").status_code == 404
