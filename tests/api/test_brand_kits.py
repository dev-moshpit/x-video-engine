"""Brand-kit endpoint tests — Phase 6."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth.clerk import ClerkPrincipal, current_user
from app.db.base import Base
from app.db.session import engine
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


def test_get_returns_nulls_when_no_kit(client: TestClient):
    res = client.get("/api/me/brand-kit")
    assert res.status_code == 200
    body = res.json()
    assert body["brand_color"] is None
    assert body["accent_color"] is None
    assert body["logo_url"] is None


def test_put_then_get_roundtrips(client: TestClient):
    payload = {
        "brand_color": "#1f6feb",
        "accent_color": "#0b0b0f",
        "text_color": "#ffffff",
        "brand_name": "Acme Studios",
        "logo_url": "https://example.invalid/logo.png",
    }
    res = client.put("/api/me/brand-kit", json=payload)
    assert res.status_code == 200
    assert res.json()["brand_color"] == "#1f6feb"

    fresh = client.get("/api/me/brand-kit").json()
    assert fresh["brand_color"] == "#1f6feb"
    assert fresh["brand_name"] == "Acme Studios"


def test_put_is_upsert(client: TestClient):
    """A second PUT updates the existing row, not creates a new one."""
    client.put("/api/me/brand-kit", json={"brand_color": "#1f6feb"})
    client.put("/api/me/brand-kit", json={"brand_color": "#dc2626"})
    res = client.get("/api/me/brand-kit").json()
    assert res["brand_color"] == "#dc2626"


def test_put_rejects_invalid_hex(client: TestClient):
    res = client.put(
        "/api/me/brand-kit",
        json={"brand_color": "not-a-hex"},
    )
    assert res.status_code == 422


def test_delete_clears_kit(client: TestClient):
    client.put("/api/me/brand-kit", json={"brand_color": "#1f6feb"})
    res = client.delete("/api/me/brand-kit")
    assert res.status_code == 204
    after = client.get("/api/me/brand-kit").json()
    assert after["brand_color"] is None


def test_delete_returns_404_when_no_kit(client: TestClient):
    res = client.delete("/api/me/brand-kit")
    assert res.status_code == 404


def test_kits_are_user_scoped(client: TestClient):
    client.put("/api/me/brand-kit", json={"brand_color": "#1f6feb"})
    app.dependency_overrides[current_user] = lambda: _principal("bob")
    res = client.get("/api/me/brand-kit")
    assert res.status_code == 200
    assert res.json()["brand_color"] is None
