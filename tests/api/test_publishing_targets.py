"""Publishing-targets API tests — Platform Phase 1."""

from __future__ import annotations

from unittest.mock import patch

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.clerk import ClerkPrincipal, current_user
from app.db.base import Base
from app.db.models import PublishingJob
from app.db.session import SessionLocal, engine
from app.main import app
from app.services import publishing_targets as publish_mod


@pytest.fixture(autouse=True)
def fresh_schema():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def fake_redis():
    fake = fakeredis.FakeRedis(decode_responses=True)
    publish_mod.set_redis(fake)
    yield fake
    publish_mod.set_redis(None)  # type: ignore[arg-type]


@pytest.fixture
def authed_client():
    fake = ClerkPrincipal(
        user_id="user_pub",
        session_id="sp",
        email="pub@example.com",
    )
    app.dependency_overrides[current_user] = lambda: fake
    yield TestClient(app)
    app.dependency_overrides.pop(current_user, None)


def test_providers_requires_auth():
    res = TestClient(app).get("/api/publishing/providers")
    assert res.status_code == 401


def test_providers_lists_youtube(authed_client: TestClient):
    res = authed_client.get(
        "/api/publishing/providers",
        headers={"Authorization": "Bearer mock"},
    )
    assert res.status_code == 200
    body = res.json()
    ids = {p["id"] for p in body["providers"]}
    assert "youtube" in ids
    yt = next(p for p in body["providers"] if p["id"] == "youtube")
    # On most CI hosts YouTube isn't configured.
    if not yt["configured"]:
        assert yt["setup_hint"]
        assert yt["error"]


def test_youtube_upload_unconfigured_503(authed_client: TestClient):
    """Without YOUTUBE_* env vars, the upload must 503 with setup hint."""
    # Force the YT env vars to be missing.
    with patch.dict("os.environ", {}, clear=False) as env:
        for key in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET",
                    "YOUTUBE_REFRESH_TOKEN"):
            env.pop(key, None)
        res = authed_client.post(
            "/api/publishing/youtube/upload",
            headers={"Authorization": "Bearer mock"},
            json={
                "video_url": "https://example.com/x.mp4",
                "title": "Hello",
            },
        )
    assert res.status_code == 503
    assert "setup hint" in res.json()["detail"].lower() or \
           "not configured" in res.json()["detail"].lower()


def test_youtube_upload_configured_creates_row(
    authed_client: TestClient, fake_redis: fakeredis.FakeRedis,
):
    """When provider reports configured=True, a row + queue entry land."""
    from apps.worker.publishing.base import PublishingProviderInfo
    from apps.worker.publishing.youtube import YouTubeProvider

    fake_info = PublishingProviderInfo(
        id="youtube", name="YouTube",
        configured=True, setup_hint="",
    )
    with patch.object(
        YouTubeProvider, "info",
        new=property(lambda self: fake_info),
    ):
        res = authed_client.post(
            "/api/publishing/youtube/upload",
            headers={"Authorization": "Bearer mock"},
            json={
                "video_url": "https://example.com/v.mp4",
                "title": "My Short",
                "description": "made with x-video-engine",
                "tags": ["shorts", "ai"],
                "privacy": "unlisted",
            },
        )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "pending"
    assert body["provider_id"] == "youtube"
    assert body["title"] == "My Short"

    db = SessionLocal()
    try:
        row = db.execute(
            select(PublishingJob).where(PublishingJob.job_id == body["job_id"])
        ).scalar_one()
        assert row.privacy == "unlisted"
        assert row.tags == ["shorts", "ai"]
    finally:
        db.close()

    queued = fake_redis.lrange("saas:publish:jobs", 0, -1)
    assert len(queued) == 1


def test_get_publishing_job_404_for_other_user():
    fake_a = ClerkPrincipal(
        user_id="user_a", session_id="sa", email="a@example.com",
    )
    app.dependency_overrides[current_user] = lambda: fake_a

    from apps.worker.publishing.base import PublishingProviderInfo
    from apps.worker.publishing.youtube import YouTubeProvider
    fake_info = PublishingProviderInfo(
        id="youtube", name="YouTube",
        configured=True, setup_hint="",
    )
    with patch.object(
        YouTubeProvider, "info",
        new=property(lambda self: fake_info),
    ):
        client = TestClient(app)
        res = client.post(
            "/api/publishing/youtube/upload",
            headers={"Authorization": "Bearer mock"},
            json={"video_url": "https://example.com/x.mp4", "title": "x"},
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
            f"/api/publishing/jobs/{job_id}",
            headers={"Authorization": "Bearer mock"},
        )
        assert res.status_code == 404
    finally:
        app.dependency_overrides.pop(current_user, None)
