"""Smoke tests for the SaaS API health endpoints (PR 1)."""

from __future__ import annotations

import sys
from pathlib import Path

# Make the api package importable when running from the project root.
_API_ROOT = Path(__file__).resolve().parents[2] / "apps" / "api"
sys.path.insert(0, str(_API_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def test_health_returns_ok():
    client = TestClient(app)
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["service"] == "api"
    assert body["version"] == app.version


def test_root_returns_doc_pointer():
    client = TestClient(app)
    res = client.get("/")
    assert res.status_code == 200
    body = res.json()
    assert body["docs"] == "/docs"
    assert "version" in body
