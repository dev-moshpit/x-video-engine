"""GET /api/video-models endpoint tests — Platform Phase 1."""

from __future__ import annotations

from unittest.mock import patch

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.clerk import ClerkPrincipal, current_user
from app.db.base import Base
from app.db.models import VideoGeneration
from app.db.session import SessionLocal, engine
from app.main import app
from app.services import video_models as videogen_mod


@pytest.fixture(autouse=True)
def fresh_schema():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def fake_redis():
    fake = fakeredis.FakeRedis(decode_responses=True)
    videogen_mod.set_redis(fake)
    yield fake
    videogen_mod.set_redis(None)  # type: ignore[arg-type]


@pytest.fixture
def authed_client():
    fake = ClerkPrincipal(
        user_id="user_models",
        session_id="sess_m",
        email="m@example.com",
    )
    app.dependency_overrides[current_user] = lambda: fake
    yield TestClient(app)
    app.dependency_overrides.pop(current_user, None)


def test_video_models_requires_auth():
    res = TestClient(app).get("/api/video-models")
    assert res.status_code == 401


def test_video_models_returns_registry(authed_client: TestClient):
    res = authed_client.get(
        "/api/video-models",
        headers={"Authorization": "Bearer mock"},
    )
    assert res.status_code == 200
    body = res.json()
    assert "providers" in body
    assert "installed" in body
    assert "total" in body
    assert body["total"] == len(body["providers"])
    assert body["total"] >= 5

    ids = {p["id"] for p in body["providers"]}
    expected = {"sdxl_parallax", "svd", "wan21", "hunyuan_video", "cogvideox"}
    assert expected.issubset(ids)

    for p in body["providers"]:
        assert p["mode"] in ("text-to-video", "image-to-video")
        assert isinstance(p["installed"], bool)
        if not p["installed"]:
            # No silent fallback — the install hint must be visible.
            assert p["install_hint"]
            assert p["error"]


# ─── Generation endpoint ───────────────────────────────────────────────


def _force_provider_installed(provider_id: str, mode: str = "text-to-video"):
    """Patch the provider's ``info`` so it reports installed=True.

    Saves the test from needing real diffusers / weights on the host.
    """
    from apps.worker.video_models.base import ProviderInfo

    fake = ProviderInfo(
        id=provider_id,
        name=provider_id,
        mode=mode,
        required_vram_gb=4.0,
        installed=True,
        install_hint="",
    )

    def factory():
        from apps.worker.video_models.provider import _REGISTRY
        cls = _REGISTRY[provider_id]
        inst = cls()
        # monkey-patch the property on the instance
        inst.__class__ = type(
            cls.__name__ + "_Patched",
            (cls,),
            {"info": property(lambda self: fake)},
        )
        return inst

    return patch(
        "apps.worker.video_models.provider._REGISTRY",
        {provider_id: factory, **{k: v for k, v in __import__(
            "apps.worker.video_models.provider", fromlist=["_REGISTRY"],
        )._REGISTRY.items() if k != provider_id}},
    )


def test_generate_unknown_provider_404(authed_client: TestClient):
    res = authed_client.post(
        "/api/video-models/generate",
        headers={"Authorization": "Bearer mock"},
        json={"provider_id": "totally_fake_xyz", "prompt": "hi"},
    )
    assert res.status_code == 404


def test_generate_uninstalled_provider_503(authed_client: TestClient):
    """If the provider is registered but not installed, 503 + hint."""
    # On most CI machines, wan21 is NOT installed. The endpoint must
    # 503 instead of silently substituting a different model.
    res = authed_client.post(
        "/api/video-models/generate",
        headers={"Authorization": "Bearer mock"},
        json={"provider_id": "wan21", "prompt": "anything"},
    )
    # If for some reason wan21 IS installed locally, the test still
    # passes (this is a 201 then). Either way, we never see a 200 for
    # a different provider.
    assert res.status_code in (201, 503)
    if res.status_code == 503:
        assert "install hint" in res.json()["detail"].lower() or \
               "not installed" in res.json()["detail"].lower()


def test_generate_image_to_video_requires_image_url(authed_client: TestClient):
    """SVD is image-to-video; calling it without image_url must 422.

    We patch the provider to report installed=True so the request
    actually hits the ``mode == "image-to-video"`` validation branch
    rather than 503-ing on availability.
    """
    from apps.worker.video_models.base import ProviderInfo
    from apps.worker.video_models.svd_provider import SVDProvider

    fake_info = ProviderInfo(
        id="svd",
        name="SVD",
        mode="image-to-video",
        required_vram_gb=12.0,
        installed=True,
        install_hint="",
    )
    with patch.object(
        SVDProvider, "info", new=property(lambda self: fake_info),
    ):
        res = authed_client.post(
            "/api/video-models/generate",
            headers={"Authorization": "Bearer mock"},
            json={"provider_id": "svd", "prompt": "ignored"},
        )
        assert res.status_code == 422
        assert "image_url" in res.json()["detail"]


def test_generate_creates_row_and_enqueues(
    authed_client: TestClient, fake_redis: fakeredis.FakeRedis,
):
    """When the provider reports installed, a row + queue entry land."""
    from apps.worker.video_models.base import ProviderInfo
    from apps.worker.video_models.sdxl_parallax_provider import (
        SDXLParallaxProvider,
    )

    fake_info = ProviderInfo(
        id="sdxl_parallax",
        name="SDXL",
        mode="text-to-video",
        required_vram_gb=4.0,
        installed=True,
        install_hint="",
    )
    with patch.object(
        SDXLParallaxProvider, "info",
        new=property(lambda self: fake_info),
    ):
        res = authed_client.post(
            "/api/video-models/generate",
            headers={"Authorization": "Bearer mock"},
            json={
                "provider_id": "sdxl_parallax",
                "prompt": "neon city",
                "duration_seconds": 3.0,
                "fps": 24,
                "aspect_ratio": "9:16",
            },
        )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "pending"
    assert body["provider_id"] == "sdxl_parallax"

    db = SessionLocal()
    try:
        row = db.execute(
            select(VideoGeneration).where(VideoGeneration.job_id == body["job_id"])
        ).scalar_one()
        assert row.prompt == "neon city"
    finally:
        db.close()

    queued = fake_redis.lrange("saas:videogen:jobs", 0, -1)
    assert len(queued) == 1


def test_get_generation_404_for_other_user():
    """Auth boundary — different Clerk user gets 404, not 403."""
    fake_a = ClerkPrincipal(
        user_id="user_aa", session_id="sa", email="a@example.com",
    )
    app.dependency_overrides[current_user] = lambda: fake_a
    client = TestClient(app)

    from apps.worker.video_models.base import ProviderInfo
    from apps.worker.video_models.sdxl_parallax_provider import (
        SDXLParallaxProvider,
    )
    fake_info = ProviderInfo(
        id="sdxl_parallax", name="SDXL", mode="text-to-video",
        required_vram_gb=4.0, installed=True, install_hint="",
    )
    with patch.object(
        SDXLParallaxProvider, "info",
        new=property(lambda self: fake_info),
    ):
        res = client.post(
            "/api/video-models/generate",
            headers={"Authorization": "Bearer mock"},
            json={"provider_id": "sdxl_parallax", "prompt": "x"},
        )
    job_id = res.json()["job_id"]
    app.dependency_overrides.pop(current_user, None)

    fake_b = ClerkPrincipal(
        user_id="user_bb", session_id="sb", email="b@example.com",
    )
    app.dependency_overrides[current_user] = lambda: fake_b
    try:
        client_b = TestClient(app)
        res = client_b.get(
            f"/api/video-models/jobs/{job_id}",
            headers={"Authorization": "Bearer mock"},
        )
        assert res.status_code == 404
    finally:
        app.dependency_overrides.pop(current_user, None)
