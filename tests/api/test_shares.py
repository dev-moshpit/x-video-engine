"""Phase 13 — share preview link tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import fakeredis
import pytest
from fastapi.testclient import TestClient

from app.auth.clerk import ClerkPrincipal, current_user
from app.db.base import Base
from app.db.models import Render
from app.db.session import SessionLocal, engine
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
}


def _seed_complete_render(client: TestClient, *, mp4_url: str = "https://r2/x.mp4") -> dict:
    """Create a project + render, then mark the render complete in the DB."""
    pid = client.post(
        "/api/projects",
        json={
            "template": "ai_story",
            "name": "p",
            "template_input": AI_STORY_INPUT,
        },
    ).json()["id"]
    render = client.post(f"/api/projects/{pid}/render").json()

    # Bypass the worker — just mark complete with a final mp4 url.
    with SessionLocal() as db:
        row = db.get(Render, uuid.UUID(render["id"]))
        row.stage = "complete"
        row.final_mp4_url = mp4_url
        row.completed_at = datetime.now(timezone.utc)
        db.commit()
    return render


# ─── Create + read ──────────────────────────────────────────────────────

def test_owner_can_create_and_read_share(client: TestClient):
    render = _seed_complete_render(client)
    res = client.post(
        f"/api/renders/{render['job_id']}/share", json={},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["is_active"] is True
    assert body["token"]
    token = body["token"]

    # Owner read returns the same row.
    again = client.get(f"/api/renders/{render['job_id']}/share")
    assert again.status_code == 200
    assert again.json()["token"] == token


def test_share_create_rejects_incomplete_render(client: TestClient):
    pid = client.post(
        "/api/projects",
        json={
            "template": "ai_story",
            "name": "p",
            "template_input": AI_STORY_INPUT,
        },
    ).json()["id"]
    render = client.post(f"/api/projects/{pid}/render").json()

    res = client.post(
        f"/api/renders/{render['job_id']}/share", json={},
    )
    assert res.status_code == 400


def test_share_recreate_keeps_token_stable(client: TestClient):
    """Creating a share twice re-activates the existing row, doesn't mint
    a new token — public links stay stable across toggles."""
    render = _seed_complete_render(client)
    a = client.post(f"/api/renders/{render['job_id']}/share", json={}).json()
    # Disable then re-create.
    client.delete(f"/api/renders/{render['job_id']}/share")
    b = client.post(f"/api/renders/{render['job_id']}/share", json={}).json()
    assert a["token"] == b["token"]
    assert b["is_active"] is True


# ─── Owner-scoped 404 ───────────────────────────────────────────────────

def test_other_user_cannot_create_share(client: TestClient):
    render = _seed_complete_render(client)
    app.dependency_overrides[current_user] = lambda: _principal("bob")
    res = client.post(
        f"/api/renders/{render['job_id']}/share", json={},
    )
    assert res.status_code == 404


def test_other_user_cannot_delete_share(client: TestClient):
    render = _seed_complete_render(client)
    client.post(f"/api/renders/{render['job_id']}/share", json={})

    app.dependency_overrides[current_user] = lambda: _principal("bob")
    res = client.delete(f"/api/renders/{render['job_id']}/share")
    assert res.status_code == 404


# ─── Public endpoint ────────────────────────────────────────────────────

def test_public_can_view_active_share(client: TestClient):
    render = _seed_complete_render(client, mp4_url="https://cdn/p.mp4")
    token = client.post(
        f"/api/renders/{render['job_id']}/share", json={},
    ).json()["token"]

    # Public endpoint is auth-less — clear the override on a bare client.
    app.dependency_overrides.pop(current_user, None)
    bare = TestClient(app)
    res = bare.get(f"/api/public/renders/{token}")
    assert res.status_code == 200
    body = res.json()
    assert body["final_mp4_url"] == "https://cdn/p.mp4"
    assert body["template"] == "ai_story"
    assert body["project_name"] == "p"
    # No private/auth-only fields leak.
    assert "user_id" not in body
    assert "template_input" not in body


def test_public_disabled_share_returns_404(client: TestClient):
    render = _seed_complete_render(client)
    token = client.post(
        f"/api/renders/{render['job_id']}/share", json={},
    ).json()["token"]
    client.delete(f"/api/renders/{render['job_id']}/share")

    app.dependency_overrides.pop(current_user, None)
    bare = TestClient(app)
    res = bare.get(f"/api/public/renders/{token}")
    assert res.status_code == 404


def test_public_unknown_token_returns_404():
    bare = TestClient(app)
    res = bare.get("/api/public/renders/does-not-exist-xyz")
    assert res.status_code == 404


def test_public_expired_share_returns_404(client: TestClient):
    render = _seed_complete_render(client)
    expires = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    token = client.post(
        f"/api/renders/{render['job_id']}/share",
        json={"expires_at": expires},
    ).json()["token"]

    app.dependency_overrides.pop(current_user, None)
    bare = TestClient(app)
    res = bare.get(f"/api/public/renders/{token}")
    assert res.status_code == 404
