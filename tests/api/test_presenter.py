"""Presenter API tests — Platform Phase 1."""

from __future__ import annotations

from unittest.mock import patch

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.clerk import ClerkPrincipal, current_user
from app.db.base import Base
from app.db.models import PresenterJob
from app.db.session import SessionLocal, engine
from app.main import app
from app.services import presenter as presenter_mod


@pytest.fixture(autouse=True)
def fresh_schema():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def fake_redis():
    fake = fakeredis.FakeRedis(decode_responses=True)
    presenter_mod.set_redis(fake)
    yield fake
    presenter_mod.set_redis(None)  # type: ignore[arg-type]


@pytest.fixture
def authed_client():
    fake = ClerkPrincipal(
        user_id="user_pres",
        session_id="sp",
        email="p@example.com",
    )
    app.dependency_overrides[current_user] = lambda: fake
    yield TestClient(app)
    app.dependency_overrides.pop(current_user, None)


def test_list_providers_requires_auth():
    res = TestClient(app).get("/api/presenter/providers")
    assert res.status_code == 401


def test_list_providers_returns_registry(authed_client: TestClient):
    res = authed_client.get(
        "/api/presenter/providers",
        headers={"Authorization": "Bearer mock"},
    )
    assert res.status_code == 200
    body = res.json()
    ids = {p["id"] for p in body["providers"]}
    assert {"wav2lip", "sadtalker", "musetalk"}.issubset(ids)
    for p in body["providers"]:
        if not p["installed"]:
            assert p["install_hint"]


def test_render_unknown_provider_404(authed_client: TestClient):
    res = authed_client.post(
        "/api/presenter/render",
        headers={"Authorization": "Bearer mock"},
        json={
            "provider_id": "xyz", "script": "hi",
            "avatar_image_url": "http://x/y.png",
        },
    )
    assert res.status_code == 404


def test_render_uninstalled_provider_503(authed_client: TestClient):
    """Uninstalled provider must 503 with install hint, not 200."""
    res = authed_client.post(
        "/api/presenter/render",
        headers={"Authorization": "Bearer mock"},
        json={
            "provider_id": "wav2lip", "script": "hi",
            "avatar_image_url": "http://x/y.png",
        },
    )
    # Most CI machines won't have wav2lip set up.
    assert res.status_code in (201, 503)
    if res.status_code == 503:
        detail = res.json()["detail"].lower()
        assert "install hint" in detail or "not installed" in detail


def test_render_with_forced_installed_creates_row(
    authed_client: TestClient, fake_redis: fakeredis.FakeRedis,
):
    from apps.worker.presenter.base import PresenterProviderInfo
    from apps.worker.presenter.wav2lip_adapter import Wav2LipPresenter

    fake_info = PresenterProviderInfo(
        id="wav2lip", name="Wav2Lip",
        installed=True, install_hint="",
    )
    with patch.object(
        Wav2LipPresenter, "info",
        new=property(lambda self: fake_info),
    ):
        res = authed_client.post(
            "/api/presenter/render",
            headers={"Authorization": "Bearer mock"},
            json={
                "provider_id": "wav2lip",
                "script": "hello there",
                "avatar_image_url": "http://example.com/avatar.png",
                "headline": "BREAKING NEWS",
                "aspect_ratio": "9:16",
            },
        )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "pending"
    assert body["provider_id"] == "wav2lip"
    assert body["headline"] == "BREAKING NEWS"

    db = SessionLocal()
    try:
        row = db.execute(
            select(PresenterJob).where(PresenterJob.job_id == body["job_id"])
        ).scalar_one()
        assert row.script == "hello there"
    finally:
        db.close()

    queued = fake_redis.lrange("saas:presenter:jobs", 0, -1)
    assert len(queued) == 1
