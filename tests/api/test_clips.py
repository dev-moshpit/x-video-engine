"""AI Clipper API tests — Platform Phase 1.

Exercises the four endpoints in ``app.routers.clips``:

  POST /api/clips/analyze              — enqueue
  GET  /api/clips/{job_id}              — poll
  POST /api/clips/{job_id}/export       — enqueue export
  GET  /api/clips/{job_id}/artifacts    — list

Auth/auth, ownership boundaries, and the "moment not found in job"
404 path are covered. The actual transcription + scoring lives in
the worker; we simulate worker output by writing rows directly.
"""

from __future__ import annotations

import uuid

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.clerk import ClerkPrincipal, current_user
from app.db.base import Base
from app.db.models import ClipArtifact, ClipJob, User
from app.db.session import SessionLocal, engine
from app.main import app
from app.services import clipper as clipper_mod


@pytest.fixture(autouse=True)
def fresh_schema():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def fake_redis():
    """Swap in fakeredis so enqueue lands on an in-memory list."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    clipper_mod.set_redis(fake)
    yield fake
    clipper_mod.set_redis(None)  # type: ignore[arg-type]


@pytest.fixture
def authed_client():
    fake = ClerkPrincipal(
        user_id="user_clipper_owner",
        session_id="sess_clip",
        email="clipper@example.com",
    )
    app.dependency_overrides[current_user] = lambda: fake
    yield TestClient(app)
    app.dependency_overrides.pop(current_user, None)


# ─── Analyze ───────────────────────────────────────────────────────────


def test_analyze_requires_auth():
    res = TestClient(app).post(
        "/api/clips/analyze",
        json={"source_url": "https://example.com/x.mp4"},
    )
    assert res.status_code == 401


def test_analyze_creates_job_and_enqueues(
    authed_client: TestClient, fake_redis: fakeredis.FakeRedis,
):
    res = authed_client.post(
        "/api/clips/analyze",
        headers={"Authorization": "Bearer mock"},
        json={"source_url": "https://example.com/podcast.mp4",
              "source_kind": "video", "language": "en"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "pending"
    assert body["progress"] == 0.0
    assert body["source_url"] == "https://example.com/podcast.mp4"
    assert body["language"] == "en"
    assert body["moments"] == []

    # Row was actually written.
    db = SessionLocal()
    try:
        row = db.execute(
            select(ClipJob).where(ClipJob.job_id == body["job_id"])
        ).scalar_one()
        assert row.source_url == "https://example.com/podcast.mp4"
    finally:
        db.close()

    # Queue got the payload.
    queued = fake_redis.lrange("saas:clipper:analyze", 0, -1)
    assert len(queued) == 1
    assert body["job_id"] in queued[0]


def test_get_clip_job_404_for_unknown_id(authed_client: TestClient):
    res = authed_client.get(
        "/api/clips/clip_nope",
        headers={"Authorization": "Bearer mock"},
    )
    assert res.status_code == 404


def test_get_clip_job_returns_moments_sorted_by_score(
    authed_client: TestClient,
):
    # First create a job via the API
    res = authed_client.post(
        "/api/clips/analyze",
        headers={"Authorization": "Bearer mock"},
        json={"source_url": "https://example.com/test.mp4"},
    )
    job_id = res.json()["job_id"]

    # Simulate the worker writing scored moments back.
    db = SessionLocal()
    try:
        job = db.execute(
            select(ClipJob).where(ClipJob.job_id == job_id)
        ).scalar_one()
        job.status = "complete"
        job.progress = 1.0
        job.duration_sec = 240.0
        job.transcript_text = "...full transcript text..."
        job.moments = [
            {
                "moment_id": "m000", "start": 0.0, "end": 30.0,
                "duration": 30.0, "text": "Low score moment",
                "score": 0.3, "score_breakdown": {}, "notes": [],
            },
            {
                "moment_id": "m001", "start": 30.0, "end": 65.0,
                "duration": 35.0, "text": "High score moment",
                "score": 0.85, "score_breakdown": {}, "notes": ["best"],
            },
        ]
        db.commit()
    finally:
        db.close()

    res = authed_client.get(
        f"/api/clips/{job_id}",
        headers={"Authorization": "Bearer mock"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "complete"
    assert len(body["moments"]) == 2
    # Sorted by score desc
    assert body["moments"][0]["moment_id"] == "m001"
    assert body["moments"][1]["moment_id"] == "m000"


# ─── Export ────────────────────────────────────────────────────────────


def _make_complete_job(authed_client: TestClient) -> str:
    """Helper: create + force-complete a clip job. Returns job_id."""
    res = authed_client.post(
        "/api/clips/analyze",
        headers={"Authorization": "Bearer mock"},
        json={"source_url": "https://example.com/v.mp4"},
    )
    job_id = res.json()["job_id"]
    db = SessionLocal()
    try:
        job = db.execute(
            select(ClipJob).where(ClipJob.job_id == job_id)
        ).scalar_one()
        job.status = "complete"
        job.moments = [
            {"moment_id": "m000", "start": 5.0, "end": 35.0,
             "duration": 30.0, "text": "Test moment.", "score": 0.7,
             "score_breakdown": {}, "notes": [], "segments": []},
        ]
        db.commit()
    finally:
        db.close()
    return job_id


def test_export_clip_requires_completed_job(authed_client: TestClient):
    # Pending job — export must 409.
    res = authed_client.post(
        "/api/clips/analyze",
        headers={"Authorization": "Bearer mock"},
        json={"source_url": "https://example.com/v.mp4"},
    )
    job_id = res.json()["job_id"]
    res = authed_client.post(
        f"/api/clips/{job_id}/export",
        headers={"Authorization": "Bearer mock"},
        json={"moment_id": "m000", "aspect": "9:16", "captions": True},
    )
    assert res.status_code == 409


def test_export_clip_404_for_unknown_moment(authed_client: TestClient):
    job_id = _make_complete_job(authed_client)
    res = authed_client.post(
        f"/api/clips/{job_id}/export",
        headers={"Authorization": "Bearer mock"},
        json={"moment_id": "m999", "aspect": "9:16", "captions": True},
    )
    assert res.status_code == 404


def test_export_clip_creates_artifact_and_enqueues(
    authed_client: TestClient, fake_redis: fakeredis.FakeRedis,
):
    job_id = _make_complete_job(authed_client)
    res = authed_client.post(
        f"/api/clips/{job_id}/export",
        headers={"Authorization": "Bearer mock"},
        json={"moment_id": "m000", "aspect": "9:16", "captions": True},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["aspect"] == "9:16"
    assert body["captions"] is True
    assert body["status"] == "pending"
    assert body["start_sec"] == 5.0
    assert body["end_sec"] == 35.0

    queued = fake_redis.lrange("saas:clipper:export", 0, -1)
    assert len(queued) == 1


def test_list_artifacts_returns_owned_only(authed_client: TestClient):
    job_id = _make_complete_job(authed_client)
    authed_client.post(
        f"/api/clips/{job_id}/export",
        headers={"Authorization": "Bearer mock"},
        json={"moment_id": "m000", "aspect": "9:16", "captions": True},
    )
    res = authed_client.get(
        f"/api/clips/{job_id}/artifacts",
        headers={"Authorization": "Bearer mock"},
    )
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 1
    assert items[0]["moment_id"] == "m000"


def test_other_user_cannot_access_job():
    """Auth boundary: a different Clerk user gets 404, not 403/200."""
    # First user creates a job.
    fake_a = ClerkPrincipal(
        user_id="user_a", session_id="sa", email="a@example.com",
    )
    app.dependency_overrides[current_user] = lambda: fake_a
    client = TestClient(app)
    res = client.post(
        "/api/clips/analyze",
        headers={"Authorization": "Bearer mock"},
        json={"source_url": "https://example.com/x.mp4"},
    )
    job_id = res.json()["job_id"]
    app.dependency_overrides.pop(current_user, None)

    # Second user attempts to read.
    fake_b = ClerkPrincipal(
        user_id="user_b", session_id="sb", email="b@example.com",
    )
    app.dependency_overrides[current_user] = lambda: fake_b
    try:
        client_b = TestClient(app)
        res = client_b.get(
            f"/api/clips/{job_id}",
            headers={"Authorization": "Bearer mock"},
        )
        assert res.status_code == 404
    finally:
        app.dependency_overrides.pop(current_user, None)
