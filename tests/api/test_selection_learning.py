"""Selection-learning preference tests (PR 13)."""

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


AI_STORY_INPUT = {
    "prompt": "Make a video about discipline at sunrise.",
    "duration": 15.0,
    "aspect": "9:16",
    "caption_style": "bold_word",
    "voice_name": "en-US-AriaNeural",
}

REDDIT_INPUT = {
    "subreddit": "AskReddit",
    "title": "weirdest neighbor",
    "body": "I had a neighbor who only wore green for a year straight.",
    "duration": 30.0,
    "caption_style": "kinetic_word",
    "voice_name": "en-US-GuyNeural",
}


def _make_render(client: TestClient, *, template: str, ti: dict) -> str:
    pid = client.post(
        "/api/projects",
        json={"template": template, "name": template, "template_input": ti},
    ).json()["id"]
    return client.post(f"/api/projects/{pid}/render").json()["id"]


def test_empty_profile_for_new_user(client: TestClient):
    res = client.get("/api/me/preferences")
    assert res.status_code == 200
    body = res.json()
    assert body["starred_count"] == 0
    assert body["rejected_count"] == 0
    assert body["templates"] == {}
    assert body["caption_styles"] == {}
    assert body["voices"] == {}
    assert body["top_template"] is None


def test_starred_renders_show_in_profile(client: TestClient):
    a = _make_render(client, template="ai_story", ti=AI_STORY_INPUT)
    b = _make_render(client, template="ai_story", ti=AI_STORY_INPUT)
    c = _make_render(client, template="reddit_story", ti=REDDIT_INPUT)
    # No-decision render — shouldn't affect counts.
    _make_render(client, template="ai_story", ti=AI_STORY_INPUT)

    client.post(f"/api/renders/{a}/star")
    client.post(f"/api/renders/{b}/star")
    client.post(f"/api/renders/{c}/star")

    body = client.get("/api/me/preferences").json()
    assert body["starred_count"] == 3
    assert body["rejected_count"] == 0
    assert body["templates"] == {"ai_story": 2, "reddit_story": 1}
    assert body["caption_styles"]["bold_word"] == 2
    assert body["caption_styles"]["kinetic_word"] == 1
    assert body["voices"]["en-US-AriaNeural"] == 2
    assert body["top_template"] == "ai_story"
    assert body["top_caption_style"] == "bold_word"
    assert body["top_voice"] == "en-US-AriaNeural"


def test_rejected_renders_count_separately(client: TestClient):
    r1 = _make_render(client, template="ai_story", ti=AI_STORY_INPUT)
    r2 = _make_render(client, template="ai_story", ti=AI_STORY_INPUT)
    client.post(f"/api/renders/{r1}/star")
    client.post(f"/api/renders/{r2}/reject")

    body = client.get("/api/me/preferences").json()
    assert body["starred_count"] == 1
    assert body["rejected_count"] == 1
    # Rejected render's pattern doesn't pollute the 'templates' count.
    assert body["templates"] == {"ai_story": 1}


def test_preferences_are_user_scoped(client: TestClient):
    rid = _make_render(client, template="ai_story", ti=AI_STORY_INPUT)
    client.post(f"/api/renders/{rid}/star")

    app.dependency_overrides[current_user] = lambda: _principal("user_bob")
    body = client.get("/api/me/preferences").json()
    assert body["starred_count"] == 0
    assert body["templates"] == {}


def test_preferences_requires_auth():
    bare = TestClient(app)
    res = bare.get("/api/me/preferences")
    assert res.status_code == 401
