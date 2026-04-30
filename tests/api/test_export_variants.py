"""Phase 13.5 — export-variant endpoint tests."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import fakeredis
import pytest
from fastapi.testclient import TestClient

from app.auth.clerk import ClerkPrincipal, current_user
from app.db.base import Base
from app.db.models import Render
from app.db.session import SessionLocal, engine
from app.main import app
from app.services import exports as exports_module
from app.services import queue as queue_module


def _principal(uid: str) -> ClerkPrincipal:
    return ClerkPrincipal(user_id=uid, session_id="s", email=f"{uid}@x.com")


@pytest.fixture(autouse=True)
def fresh_schema_and_queue():
    Base.metadata.create_all(engine)
    fake = fakeredis.FakeRedis(decode_responses=True)
    queue_module.set_redis(fake)
    exports_module.set_redis(fake)
    yield fake
    queue_module.set_redis(None)
    exports_module.set_redis(None)
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


def _seed_complete_render(client: TestClient) -> dict:
    pid = client.post(
        "/api/projects",
        json={
            "template": "ai_story",
            "name": "p",
            "template_input": AI_STORY_INPUT,
        },
    ).json()["id"]
    render = client.post(f"/api/projects/{pid}/render").json()

    with SessionLocal() as db:
        row = db.get(Render, uuid.UUID(render["id"]))
        row.stage = "complete"
        row.final_mp4_url = "https://r2/x.mp4"
        row.completed_at = datetime.now(timezone.utc)
        db.commit()
    return render


# ─── Enqueue ───────────────────────────────────────────────────────────

def test_export_variant_enqueues_artifact(
    client: TestClient, fresh_schema_and_queue: fakeredis.FakeRedis,
):
    render = _seed_complete_render(client)
    res = client.post(
        f"/api/renders/{render['job_id']}/export-variant",
        json={"aspect": "1:1", "captions": True},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["aspect"] == "1:1"
    assert body["captions"] is True
    assert body["status"] == "pending"

    # Job is on the export queue.
    raw = fresh_schema_and_queue.lpop("saas:export:jobs")
    assert raw is not None
    payload = json.loads(raw)
    assert payload["aspect"] == "1:1"
    assert payload["src_url"] == "https://r2/x.mp4"
    assert payload["job_id"] == render["job_id"]


def test_export_variant_artifact_persists_for_listing(client: TestClient):
    render = _seed_complete_render(client)
    client.post(
        f"/api/renders/{render['job_id']}/export-variant",
        json={"aspect": "9:16", "captions": False},
    )
    rows = client.get(f"/api/renders/{render['job_id']}/artifacts").json()
    assert len(rows) == 1
    assert rows[0]["aspect"] == "9:16"
    assert rows[0]["captions"] is False


# ─── Validation ────────────────────────────────────────────────────────

def test_export_variant_rejects_invalid_aspect(client: TestClient):
    render = _seed_complete_render(client)
    res = client.post(
        f"/api/renders/{render['job_id']}/export-variant",
        json={"aspect": "4:3", "captions": True},
    )
    assert res.status_code == 422


def test_export_variant_rejects_incomplete_render(client: TestClient):
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
        f"/api/renders/{render['job_id']}/export-variant",
        json={"aspect": "16:9", "captions": True},
    )
    assert res.status_code == 400


# ─── Owner scope ───────────────────────────────────────────────────────

def test_export_variant_owner_scoped(client: TestClient):
    render = _seed_complete_render(client)
    app.dependency_overrides[current_user] = lambda: _principal("bob")
    res = client.post(
        f"/api/renders/{render['job_id']}/export-variant",
        json={"aspect": "16:9", "captions": True},
    )
    assert res.status_code == 404


def test_artifacts_listing_owner_scoped(client: TestClient):
    render = _seed_complete_render(client)
    client.post(
        f"/api/renders/{render['job_id']}/export-variant",
        json={"aspect": "16:9", "captions": True},
    )
    app.dependency_overrides[current_user] = lambda: _principal("bob")
    res = client.get(f"/api/renders/{render['job_id']}/artifacts")
    assert res.status_code == 404
