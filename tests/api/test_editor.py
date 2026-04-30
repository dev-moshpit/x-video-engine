"""Editor API tests — Platform Phase 1."""

from __future__ import annotations

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.clerk import ClerkPrincipal, current_user
from app.db.base import Base
from app.db.models import EditorJob
from app.db.session import SessionLocal, engine
from app.main import app
from app.services import editor as editor_mod


@pytest.fixture(autouse=True)
def fresh_schema():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def fake_redis():
    fake = fakeredis.FakeRedis(decode_responses=True)
    editor_mod.set_redis(fake)
    yield fake
    editor_mod.set_redis(None)  # type: ignore[arg-type]


@pytest.fixture
def authed_client():
    fake = ClerkPrincipal(
        user_id="user_editor",
        session_id="sess_ed",
        email="ed@example.com",
    )
    app.dependency_overrides[current_user] = lambda: fake
    yield TestClient(app)
    app.dependency_overrides.pop(current_user, None)


def test_editor_process_requires_auth():
    res = TestClient(app).post(
        "/api/editor/process",
        json={"source_url": "https://x/y.mp4", "aspect": "9:16"},
    )
    assert res.status_code == 401


def test_editor_process_creates_job_and_enqueues(
    authed_client: TestClient, fake_redis: fakeredis.FakeRedis,
):
    res = authed_client.post(
        "/api/editor/process",
        headers={"Authorization": "Bearer mock"},
        json={
            "source_url": "https://example.com/clip.mp4",
            "trim_start": 5.0,
            "trim_end": 30.0,
            "aspect": "9:16",
            "captions": True,
            "caption_language": "en",
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "pending"
    assert body["aspect"] == "9:16"
    assert body["trim_start"] == 5.0
    assert body["trim_end"] == 30.0
    assert body["captions"] is True

    db = SessionLocal()
    try:
        row = db.execute(
            select(EditorJob).where(EditorJob.job_id == body["job_id"])
        ).scalar_one()
        assert row.aspect == "9:16"
    finally:
        db.close()

    queued = fake_redis.lrange("saas:editor:jobs", 0, -1)
    assert len(queued) == 1
    assert body["job_id"] in queued[0]


def test_editor_process_rejects_inverted_trim(authed_client: TestClient):
    res = authed_client.post(
        "/api/editor/process",
        headers={"Authorization": "Bearer mock"},
        json={
            "source_url": "https://example.com/x.mp4",
            "trim_start": 30.0,
            "trim_end": 5.0,
            "aspect": "1:1",
            "captions": False,
        },
    )
    assert res.status_code == 422


def test_get_editor_job_404_for_other_user():
    fake_a = ClerkPrincipal(
        user_id="user_a", session_id="sa", email="a@example.com",
    )
    app.dependency_overrides[current_user] = lambda: fake_a
    client = TestClient(app)
    res = client.post(
        "/api/editor/process",
        headers={"Authorization": "Bearer mock"},
        json={"source_url": "https://example.com/x.mp4", "aspect": "9:16"},
    )
    job_id = res.json()["job_id"]
    app.dependency_overrides.pop(current_user, None)

    fake_b = ClerkPrincipal(
        user_id="user_b", session_id="sb", email="b@example.com",
    )
    app.dependency_overrides[current_user] = lambda: fake_b
    try:
        client_b = TestClient(app)
        res = client_b.get(
            f"/api/editor/{job_id}",
            headers={"Authorization": "Bearer mock"},
        )
        assert res.status_code == 404
    finally:
        app.dependency_overrides.pop(current_user, None)


def test_editor_process_accepts_aspect_source(authed_client: TestClient):
    res = authed_client.post(
        "/api/editor/process",
        headers={"Authorization": "Bearer mock"},
        json={
            "source_url": "https://example.com/x.mp4",
            "aspect": "source",
            "captions": False,
        },
    )
    assert res.status_code == 201
    assert res.json()["aspect"] == "source"
