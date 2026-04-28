"""Media library endpoint tests (Phase 2.5).

Search is mocked at the service-function boundary so tests don't hit
Pexels/Pixabay during CI. Save / list / delete go through the real DB.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.clerk import ClerkPrincipal, current_user
from app.db.base import Base
from app.db.session import engine
from app.main import app
from app.routers import media as media_router
from app.services.media import SearchHit


def _principal(uid: str) -> ClerkPrincipal:
    return ClerkPrincipal(user_id=uid, session_id="s", email=f"{uid}@x.com")


@pytest.fixture(autouse=True)
def fresh_schema():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client():
    app.dependency_overrides[current_user] = lambda: _principal("user_alice")
    yield TestClient(app)
    app.dependency_overrides.pop(current_user, None)


@pytest.fixture
def patch_search(monkeypatch):
    """Replace ``app.services.media.search`` with a fixture-driven stub.

    The router calls it as ``provider_search``, which is the imported
    name. Patch the *router*'s reference so the stub takes effect.
    """
    captured: dict[str, Any] = {}
    fixture_hits: list[SearchHit] = []
    fixture_warnings: list[str] = []

    def fake_search(**kwargs):
        captured["kwargs"] = kwargs
        return list(fixture_hits), list(fixture_warnings)

    monkeypatch.setattr(media_router, "provider_search", fake_search)
    return captured, fixture_hits, fixture_warnings


def test_search_returns_provider_hits_unchanged(client: TestClient, patch_search):
    captured, fixture_hits, _w = patch_search
    fixture_hits.append(
        SearchHit(
            provider="pexels", provider_asset_id="123",
            kind="video",
            url="https://example.invalid/video.mp4",
            thumbnail_url="https://example.invalid/thumb.jpg",
            width=1080, height=1920, duration_sec=12.0,
            orientation="vertical",
            tags=[], attribution="Video by tester via Pexels",
        )
    )
    res = client.post(
        "/api/media/search",
        json={"query": "skateboard", "kind": "video", "orientation": "vertical"},
    )
    assert res.status_code == 200
    body = res.json()
    assert len(body["hits"]) == 1
    h = body["hits"][0]
    assert h["provider"] == "pexels"
    assert h["url"].endswith(".mp4")
    assert h["orientation"] == "vertical"
    assert captured["kwargs"]["query"] == "skateboard"
    assert captured["kwargs"]["kind"] == "video"


def test_search_surfaces_provider_warnings(client: TestClient, patch_search):
    _captured, _hits, fixture_warnings = patch_search
    fixture_warnings.append("PEXELS_API_KEY not set — Pexels skipped")
    res = client.post(
        "/api/media/search",
        json={"query": "anything"},
    )
    assert res.status_code == 200
    assert "PEXELS_API_KEY" in " ".join(res.json()["warnings"])


def test_save_then_list_then_delete(client: TestClient):
    payload = {
        "provider": "pexels",
        "provider_asset_id": "123",
        "kind": "video",
        "url": "https://example.invalid/video.mp4",
        "thumbnail_url": "https://example.invalid/thumb.jpg",
        "width": 1080, "height": 1920,
        "duration_sec": 12.0,
        "orientation": "vertical",
        "tags": ["skateboard", "outdoor"],
        "attribution": "Video by tester via Pexels",
    }
    save_res = client.post("/api/media/save", json=payload)
    assert save_res.status_code == 201
    saved = save_res.json()
    assert saved["url"] == payload["url"]
    asset_id = saved["id"]

    list_res = client.get("/api/media")
    assert list_res.status_code == 200
    items = list_res.json()
    assert len(items) == 1
    assert items[0]["id"] == asset_id

    # Filter by orientation.
    list_h = client.get("/api/media?orientation=horizontal")
    assert list_h.json() == []

    del_res = client.delete(f"/api/media/{asset_id}")
    assert del_res.status_code == 204
    assert client.get("/api/media").json() == []


def test_save_requires_auth(client: TestClient):
    """Without a current_user override the endpoint must reject."""
    app.dependency_overrides.pop(current_user, None)
    try:
        res = client.post(
            "/api/media/save",
            json={
                "provider": "pexels", "provider_asset_id": "1",
                "kind": "video", "url": "https://example.invalid/v.mp4",
            },
        )
        assert res.status_code in (401, 403)
    finally:
        app.dependency_overrides[current_user] = lambda: _principal("user_alice")


def test_delete_other_users_asset_returns_404(client: TestClient):
    """A user must not be able to delete someone else's saved asset."""
    saved = client.post(
        "/api/media/save",
        json={
            "provider": "pexels", "provider_asset_id": "9",
            "kind": "image", "url": "https://example.invalid/x.jpg",
        },
    ).json()
    asset_id = saved["id"]

    app.dependency_overrides[current_user] = lambda: _principal("user_bob")
    res = client.delete(f"/api/media/{asset_id}")
    assert res.status_code == 404
