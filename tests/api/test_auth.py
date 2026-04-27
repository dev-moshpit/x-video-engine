"""Auth tests for the SaaS API (PR 2).

Three paths exercised:
  1. /api/me without an Authorization header → 401
  2. /api/me with an invalid bearer token → 401
  3. /api/me with the ``current_user`` dep overridden → 200 with principal

We don't make real Clerk calls — JWKS-based verification is exercised
in integration tests once a real Clerk app is provisioned.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# The auth module reads CLERK_JWT_ISSUER at import time. Set a non-
# routable URL before the import so accidental network calls fail fast
# instead of hanging.
os.environ.setdefault("CLERK_JWT_ISSUER", "https://example.invalid")

_API_ROOT = Path(__file__).resolve().parents[2] / "apps" / "api"
sys.path.insert(0, str(_API_ROOT))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth.clerk import ClerkPrincipal, current_user  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def authed_client():
    fake = ClerkPrincipal(
        user_id="user_test123",
        session_id="sess_test",
        email="dev@example.com",
    )
    app.dependency_overrides[current_user] = lambda: fake
    yield TestClient(app)
    app.dependency_overrides.pop(current_user, None)


def test_me_without_token_returns_401(client):
    res = client.get("/api/me")
    assert res.status_code == 401
    assert res.headers.get("WWW-Authenticate") == "Bearer"


def test_me_with_malformed_token_returns_401(client):
    res = client.get(
        "/api/me",
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert res.status_code == 401


def test_me_with_overridden_dep_returns_principal(authed_client):
    res = authed_client.get(
        "/api/me",
        headers={"Authorization": "Bearer mock"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["user_id"] == "user_test123"
    assert body["session_id"] == "sess_test"
    assert body["email"] == "dev@example.com"


def test_health_remains_public(client):
    res = client.get("/health")
    assert res.status_code == 200
