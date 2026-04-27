"""POST /api/projects/:id/plan tests (PR 4).

This is the first endpoint that calls into ``xvideo.prompt_native``
synchronously. Cheap, deterministic, no GPU.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth.clerk import ClerkPrincipal, current_user
from app.db.base import Base
from app.db.session import engine
from app.main import app


@pytest.fixture(autouse=True)
def fresh_schema():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client():
    fake = ClerkPrincipal(
        user_id="user_planner", session_id="sess", email="p@example.com",
    )
    app.dependency_overrides[current_user] = lambda: fake
    yield TestClient(app)
    app.dependency_overrides.pop(current_user, None)


def _create_ai_story(client: TestClient, prompt: str = "Discipline at 5am") -> str:
    res = client.post(
        "/api/projects",
        json={
            "template": "ai_story",
            "name": "p",
            "template_input": {
                "prompt": "Make a video about " + prompt,
                "duration": 20.0,
                "aspect": "9:16",
            },
        },
    )
    return res.json()["id"]


def test_ai_story_plan_preview(client: TestClient):
    pid = _create_ai_story(client)
    res = client.post(f"/api/projects/{pid}/plan", json={"variations": 1, "seed": 42})
    assert res.status_code == 200
    body = res.json()
    assert len(body["plans"]) == 1

    plan_entry = body["plans"][0]
    assert "video_plan" in plan_entry
    assert "score" in plan_entry
    assert "warnings" in plan_entry

    plan = plan_entry["video_plan"]
    # Sanity: the engine returned a real plan, not a stub.
    assert plan["title"]
    assert plan["hook"]
    assert plan["concept"]
    assert isinstance(plan["scenes"], list) and len(plan["scenes"]) >= 3
    # plan.seed is derived per-variation from (input_seed, variation_id);
    # it's an int, but not necessarily equal to the input seed itself.
    # Determinism is asserted in test_seed_produces_deterministic_plan.
    assert isinstance(plan["seed"], int)

    score = plan_entry["score"]
    assert 0.0 <= score["total"] <= 100.0


def test_ai_story_plan_variations(client: TestClient):
    pid = _create_ai_story(client, "consistency over motivation")
    res = client.post(
        f"/api/projects/{pid}/plan",
        json={"variations": 3, "seed": 7},
    )
    assert res.status_code == 200
    body = res.json()
    assert len(body["plans"]) == 3
    # Different variation_id per plan.
    variations = [p["video_plan"]["variation_id"] for p in body["plans"]]
    assert sorted(variations) == [0, 1, 2]


def test_seed_produces_deterministic_plan(client: TestClient):
    pid = _create_ai_story(client, "the morning the comeback started")
    a = client.post(
        f"/api/projects/{pid}/plan",
        json={"variations": 1, "seed": 1234},
    ).json()
    b = client.post(
        f"/api/projects/{pid}/plan",
        json={"variations": 1, "seed": 1234},
    ).json()
    assert a["plans"][0]["video_plan"]["title"] == b["plans"][0]["video_plan"]["title"]
    assert a["plans"][0]["video_plan"]["hook"] == b["plans"][0]["video_plan"]["hook"]


def test_reddit_story_plan_preview(client: TestClient):
    res = client.post(
        "/api/projects",
        json={
            "template": "reddit_story",
            "name": "Reddit test",
            "template_input": {
                "subreddit": "AskReddit",
                "title": "What's your weirdest neighbor story?",
                "body": "I lived next to a guy who only wore green for a whole year.",
                "duration": 25.0,
            },
        },
    )
    pid = res.json()["id"]

    res = client.post(f"/api/projects/{pid}/plan", json={"variations": 1, "seed": 99})
    assert res.status_code == 200
    plan = res.json()["plans"][0]["video_plan"]
    # The synthetic prompt should have been sent in.
    assert plan["title"]
    assert isinstance(plan["scenes"], list) and len(plan["scenes"]) >= 3


def test_voiceover_plan_returns_422(client: TestClient):
    res = client.post(
        "/api/projects",
        json={
            "template": "voiceover",
            "name": "VO test",
            "template_input": {
                "script": "Once upon a time, there was a deep voice and a script.",
                "background_color": "#0b0b0f",
            },
        },
    )
    pid = res.json()["id"]

    res = client.post(f"/api/projects/{pid}/plan", json={"variations": 1})
    assert res.status_code == 422
    assert "no plan preview" in res.json()["detail"].lower()


def test_plan_preview_404_for_other_users_project(client: TestClient):
    pid = _create_ai_story(client)

    other = ClerkPrincipal(
        user_id="user_other", session_id="sess2", email="o@example.com",
    )
    app.dependency_overrides[current_user] = lambda: other

    res = client.post(f"/api/projects/{pid}/plan", json={"variations": 1})
    assert res.status_code == 404
