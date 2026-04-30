"""Phase 9 — saved-prompt + insights endpoint tests."""

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
    app.dependency_overrides[current_user] = lambda: _principal("alice")
    yield TestClient(app)
    app.dependency_overrides.pop(current_user, None)


AI_STORY_INPUT = {
    "prompt": "Make a video about discipline at sunrise.",
    "duration": 15.0,
    "aspect": "9:16",
    "caption_style": "bold_word",
}


# ─── Saved prompts CRUD ─────────────────────────────────────────────────

def test_create_and_list_saved_prompts(client: TestClient):
    res = client.post(
        "/api/me/saved-prompts",
        json={
            "template": "ai_story",
            "label": "Discipline starter",
            "template_input": AI_STORY_INPUT,
        },
    )
    assert res.status_code == 201, res.text
    sp = res.json()
    assert sp["label"] == "Discipline starter"
    assert sp["template"] == "ai_story"
    assert sp["use_count"] == 0

    rows = client.get("/api/me/saved-prompts").json()
    assert len(rows) == 1
    assert rows[0]["id"] == sp["id"]


def test_create_saved_prompt_validates_template_input(client: TestClient):
    res = client.post(
        "/api/me/saved-prompts",
        json={
            "template": "ai_story",
            "label": "broken",
            "template_input": {"prompt": "x"},  # too short
        },
    )
    assert res.status_code == 422


def test_use_saved_prompt_creates_project(client: TestClient):
    sp = client.post(
        "/api/me/saved-prompts",
        json={
            "template": "ai_story",
            "label": "starter",
            "template_input": AI_STORY_INPUT,
        },
    ).json()

    res = client.post(
        f"/api/me/saved-prompts/{sp['id']}/use",
        json={"name": "From preset"},
    )
    assert res.status_code == 200
    project = res.json()
    assert project["name"] == "From preset"
    assert project["template"] == "ai_story"
    # Original template_input is duplicated, not shared by reference.
    assert project["template_input"]["prompt"].startswith("Make a video")

    # use_count + last_used_at bumped.
    after = client.get("/api/me/saved-prompts").json()
    assert after[0]["use_count"] == 1
    assert after[0]["last_used_at"] is not None


def test_update_and_delete_saved_prompt(client: TestClient):
    sp = client.post(
        "/api/me/saved-prompts",
        json={
            "template": "ai_story",
            "label": "old",
            "template_input": AI_STORY_INPUT,
        },
    ).json()

    upd = client.patch(
        f"/api/me/saved-prompts/{sp['id']}",
        json={"label": "renamed"},
    )
    assert upd.status_code == 200
    assert upd.json()["label"] == "renamed"

    rm = client.delete(f"/api/me/saved-prompts/{sp['id']}")
    assert rm.status_code == 204
    assert client.get("/api/me/saved-prompts").json() == []


def test_saved_prompts_user_scoped(client: TestClient):
    sp = client.post(
        "/api/me/saved-prompts",
        json={
            "template": "ai_story",
            "label": "alice's",
            "template_input": AI_STORY_INPUT,
        },
    ).json()

    app.dependency_overrides[current_user] = lambda: _principal("bob")
    rows = client.get("/api/me/saved-prompts").json()
    assert rows == []
    res = client.delete(f"/api/me/saved-prompts/{sp['id']}")
    assert res.status_code == 404


# ─── Insights ───────────────────────────────────────────────────────────

def test_insights_for_new_user_shows_starters(client: TestClient):
    res = client.get("/api/me/insights")
    assert res.status_code == 200
    body = res.json()
    assert body["is_new_user"] is True
    assert body["total_renders"] == 0
    assert body["best_template"] is None
    # Always at least one starter suggestion seeded.
    assert len(body["suggestions"]) >= 1
    for s in body["suggestions"]:
        assert s["template"]
        assert s["label"]


def test_insights_surfaces_best_template_after_history(client: TestClient):
    pid = client.post(
        "/api/projects",
        json={
            "template": "ai_story",
            "name": "p",
            "template_input": AI_STORY_INPUT,
        },
    ).json()["id"]
    a = client.post(f"/api/projects/{pid}/render").json()["id"]
    b = client.post(f"/api/projects/{pid}/render").json()["id"]
    client.post(f"/api/renders/{a}/star")
    client.post(f"/api/renders/{b}/star")

    body = client.get("/api/me/insights").json()
    assert body["is_new_user"] is False
    assert body["total_renders"] == 2
    assert body["starred_renders"] == 2
    assert body["best_template"] is not None
    assert body["best_template"]["template"] == "ai_story"
    assert body["best_template"]["star_rate"] == 1.0
    # Suggestions should include the best template at the top.
    assert any(s["template"] == "ai_story" for s in body["suggestions"])


def test_insights_requires_auth():
    bare = TestClient(app)
    assert bare.get("/api/me/insights").status_code == 401
