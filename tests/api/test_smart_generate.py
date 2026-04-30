"""Phase 8 — smart-generate endpoint + boost-from-history tests."""

from __future__ import annotations

import fakeredis
import pytest
from fastapi.testclient import TestClient

from app.auth.clerk import ClerkPrincipal, current_user
from app.db.base import Base
from app.db.session import engine
from app.main import app
from app.services import queue as queue_module
from app.services.selection_learning import (
    compute_plan_score_boost,
    compute_user_preferences,
)


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
    "prompt": "Make a video about discipline at sunrise",
    "duration": 15.0,
    "aspect": "9:16",
    "caption_style": "bold_word",
    "voice_name": "en-US-AriaNeural",
}


def _make_project(client: TestClient, *, template="ai_story", ti=None) -> str:
    body = ti or AI_STORY_INPUT
    res = client.post(
        "/api/projects",
        json={"template": template, "name": template, "template_input": body},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


# ─── /generate-smart ────────────────────────────────────────────────────

def test_smart_generate_picks_best_of_n(client: TestClient):
    """With render_top=0 (preview-only), endpoint returns ranked candidates
    and never enqueues a render. Should not consume credits."""
    pid = _make_project(client)
    res = client.post(
        f"/api/projects/{pid}/generate-smart",
        json={"candidates": 3, "render_top": 0},
    )
    assert res.status_code == 200, res.text
    body = res.json()

    assert len(body["plans"]) == 3
    assert 0 <= body["best_index"] < 3
    assert body["best_plan"]["video_plan"]["title"]
    assert body["rendered"] == []
    # boosted_score >= baseline (cold start: no boost yet)
    assert body["boosted_score"] >= 0
    assert isinstance(body["reasoning"], list) and len(body["reasoning"]) >= 1


def test_smart_generate_enqueues_render(client: TestClient):
    pid = _make_project(client)
    res = client.post(
        f"/api/projects/{pid}/generate-smart",
        json={"candidates": 2, "render_top": 1},
    )
    assert res.status_code == 200
    body = res.json()
    assert len(body["rendered"]) == 1
    r = body["rendered"][0]
    assert r["stage"] == "pending"
    assert r["job_id"]


def test_smart_generate_gates_on_credits(client: TestClient):
    """When the user is out of credits, render_top>0 returns 402."""
    from app.db.session import SessionLocal
    from app.db.models import CreditLedger
    from sqlalchemy import select
    from app.db.models import User

    pid = _make_project(client)
    # Drain credits.
    with SessionLocal() as s:
        u = s.execute(select(User).where(User.email == "alice@x.com")).scalar_one()
        s.add(CreditLedger(user_id=u.id, amount=-100, reason="drain_for_test"))
        s.commit()

    res = client.post(
        f"/api/projects/{pid}/generate-smart",
        json={"candidates": 2, "render_top": 1},
    )
    assert res.status_code == 402


def test_smart_generate_direct_render_template(client: TestClient):
    """voiceover has no plan stage — endpoint should still return a stub
    plan response and (when render_top>0) enqueue the render."""
    pid = _make_project(
        client,
        template="voiceover",
        ti={
            "script": "Hello there from the auto-render path.",
            "background_color": "#0b0b0f",
            "caption_style": "bold_word",
            "aspect": "9:16",
        },
    )
    res = client.post(
        f"/api/projects/{pid}/generate-smart",
        json={"candidates": 3, "render_top": 1},
    )
    assert res.status_code == 200
    body = res.json()
    assert len(body["plans"]) == 1
    assert "direct-render" in body["plans"][0]["video_plan"]["concept"].lower()
    assert len(body["rendered"]) == 1


def test_smart_generate_404_for_other_user(client: TestClient):
    pid = _make_project(client)
    app.dependency_overrides[current_user] = lambda: _principal("bob")
    res = client.post(
        f"/api/projects/{pid}/generate-smart",
        json={"candidates": 2, "render_top": 0},
    )
    assert res.status_code == 404


# ─── Selection learning v2 ──────────────────────────────────────────────

def test_preferences_include_hook_and_duration(client: TestClient):
    """Phase 8: starred renders now contribute to hook_starts +
    duration_buckets in the profile."""
    p1 = _make_project(client)
    r1 = client.post(f"/api/projects/{p1}/render").json()["id"]
    client.post(f"/api/renders/{r1}/star")

    body = client.get("/api/me/preferences").json()
    assert "hook_starts" in body
    assert "duration_buckets" in body
    assert body["duration_buckets"]["8-15s"] == 1
    # The hook_start derives from the prompt opener.
    assert body["top_hook_start"] is not None


def test_compute_plan_score_boost_rewards_matching_hook():
    profile = {
        "hook_starts": {"i used to": 2},
        "duration_buckets": {"16-30s": 3},
        "top_caption_style": "bold_word",
    }
    plan = {
        "hook": "I used to think I was lazy.",
        "scenes": [{"duration": 5}, {"duration": 5}, {"duration": 8}],
        "caption_style": "bold_word",
    }
    delta, reasons = compute_plan_score_boost(plan, profile, template="ai_story")
    assert delta > 0
    # Hook boost should be present in reasons.
    assert any("hook" in r for r in reasons)
    # Duration boost — total 18s ∈ "16-30s" with count 3 ≥ 2.
    assert any("length" in r or "16-30s" in r for r in reasons)
    # Caption boost.
    assert any("caption" in r.lower() for r in reasons)


def test_compute_plan_score_boost_caps_at_five():
    profile = {
        "hook_starts": {"this is": 50},
        "duration_buckets": {"16-30s": 50},
        "top_caption_style": "bold_word",
    }
    plan = {
        "hook": "this is the way",
        "scenes": [{"duration": 20}],
        "caption_style": "bold_word",
    }
    delta, _ = compute_plan_score_boost(plan, profile, template="ai_story")
    assert delta <= 5.0


def test_compute_plan_score_boost_no_history_returns_zero():
    profile = {
        "hook_starts": {},
        "duration_buckets": {},
        "top_caption_style": None,
    }
    plan = {"hook": "anything", "scenes": [{"duration": 12}]}
    delta, reasons = compute_plan_score_boost(plan, profile, template="ai_story")
    assert delta == 0.0
    assert reasons == []
