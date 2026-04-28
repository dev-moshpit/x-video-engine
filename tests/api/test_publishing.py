"""Publishing endpoint tests — Phase 7.

Verifies the heuristic title/description/hashtag generator returns
sensible output for templates with and without an attached VideoPlan.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.auth.clerk import ClerkPrincipal, current_user
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.db.models import Project, Render, User, VideoPlan
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
    app.dependency_overrides[current_user] = lambda: _principal("alice")
    yield TestClient(app)
    app.dependency_overrides.pop(current_user, None)


def _make_project(client: TestClient, *, template: str, ti: dict) -> str:
    return client.post(
        "/api/projects",
        json={"template": template, "name": "test", "template_input": ti},
    ).json()["id"]


def test_metadata_for_voiceover_uses_script_keywords(client: TestClient):
    pid = _make_project(
        client,
        template="voiceover",
        ti={
            "script": (
                "Discipline beats motivation every single morning. "
                "Discipline outlasts mood. Discipline is the foundation."
            ),
            "background_color": "#0b0b0f",
            "caption_style": "bold_word",
            "aspect": "9:16",
        },
    )
    res = client.get(f"/api/projects/{pid}/publish-metadata")
    assert res.status_code == 200
    body = res.json()
    assert body["title"]
    assert body["description"]
    # Voiceover baseline tags must show up.
    assert "#voiceover" in body["hashtags"]
    # Most-frequent script word ("discipline") should be in hashtags.
    assert any("discipline" in h.lower() for h in body["hashtags"])


def test_metadata_for_fake_text_uses_template_baseline(client: TestClient):
    pid = _make_project(
        client,
        template="fake_text",
        ti={
            "style": "ios", "theme": "dark",
            "chat_title": "Mom",
            "messages": [
                {"sender": "them", "text": "Where are you?",
                 "typing_ms": 800, "hold_ms": 1500},
                {"sender": "me", "text": "On my way home.",
                 "typing_ms": 800, "hold_ms": 1500},
            ],
            "aspect": "9:16",
            "narrate": False,
        },
    )
    res = client.get(f"/api/projects/{pid}/publish-metadata")
    body = res.json()
    assert "#fakemessages" in body["hashtags"]
    # Title is set even without a plan.
    assert len(body["title"]) > 0
    assert len(body["alternates"]) <= 3


def test_metadata_uses_video_plan_title_when_available(client: TestClient):
    """When a render completes with a VideoPlan, prefer that title +
    hook + cta over the script-derived defaults."""
    pid = _make_project(
        client,
        template="ai_story",
        ti={
            "prompt": "Make a video about discipline at sunrise.",
            "duration": 15.0, "aspect": "9:16",
        },
    )
    # Simulate a completed render with a VideoPlan attached.
    db = SessionLocal()
    try:
        proj = db.get(Project, uuid.UUID(pid))
        ren = Render(
            project_id=proj.id,
            job_id=uuid.uuid4().hex[:16],
            stage="complete",
            progress=1.0,
        )
        db.add(ren)
        db.flush()
        plan = VideoPlan(
            render_id=ren.id,
            plan_json={
                "title": "Wake Up Before The World Does",
                "hook": "Discipline doesn't ask how you feel.",
                "cta": "Save this if you needed it today.",
                "scenes": [], "voiceover_lines": [],
            },
            score_json={},
            prompt_hash="h",
            seed=42,
        )
        db.add(plan)
        db.commit()
    finally:
        db.close()

    res = client.get(f"/api/projects/{pid}/publish-metadata")
    body = res.json()
    assert body["title"] == "Wake Up Before The World Does"
    # Hook + CTA combined into description.
    assert "Discipline doesn't ask" in body["description"]
    assert "Save this" in body["description"]


def test_metadata_returns_404_for_other_users_project(client: TestClient):
    pid = _make_project(
        client,
        template="voiceover",
        ti={"script": "alice's script for the voiceover render."},
    )
    app.dependency_overrides[current_user] = lambda: _principal("bob")
    res = client.get(f"/api/projects/{pid}/publish-metadata")
    assert res.status_code == 404


def test_metadata_caps_hashtags_at_twelve(client: TestClient):
    pid = _make_project(
        client,
        template="voiceover",
        ti={
            "script": (
                "Cinema photography sunset desert mountain ocean forest river "
                "lake valley ridge canyon crater meadow island archipelago."
            ),
        },
    )
    body = client.get(f"/api/projects/{pid}/publish-metadata").json()
    assert len(body["hashtags"]) <= 12
