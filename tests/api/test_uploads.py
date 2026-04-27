"""Presigned-upload endpoint tests (PR 7)."""

from __future__ import annotations

import os

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from app.auth.clerk import ClerkPrincipal, current_user
from app.db.base import Base
from app.db.session import engine
from app.main import app
from app.services import storage as api_storage


def _principal(uid: str = "user_alice") -> ClerkPrincipal:
    return ClerkPrincipal(user_id=uid, session_id="s", email=f"{uid}@x.com")


@pytest.fixture(autouse=True)
def fresh_schema():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def moto_s3():
    with mock_aws():
        os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
        client = boto3.client("s3", region_name="us-east-1")
        api_storage.set_s3_client(client)
        yield client
        api_storage.set_s3_client(None)


@pytest.fixture
def client():
    app.dependency_overrides[current_user] = lambda: _principal()
    yield TestClient(app)
    app.dependency_overrides.pop(current_user, None)


def test_sign_returns_put_url(moto_s3, client: TestClient):
    res = client.post(
        "/api/uploads/sign",
        json={"kind": "audio", "content_type": "audio/mpeg"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["method"] == "PUT"
    assert body["url"].startswith("http")
    assert body["key"].startswith("uploads/audio/")
    assert body["content_type"] == "audio/mpeg"
    assert 30 <= body["expires_in"] <= 3600


def test_sign_rejects_unknown_kind(moto_s3, client: TestClient):
    res = client.post(
        "/api/uploads/sign",
        json={"kind": "executable", "content_type": "x/y"},
    )
    assert res.status_code == 422


def test_sign_requires_auth(moto_s3):
    # No dependency override = real auth required
    app.dependency_overrides.pop(current_user, None)
    bare = TestClient(app)
    res = bare.post(
        "/api/uploads/sign",
        json={"kind": "audio", "content_type": "audio/mpeg"},
    )
    assert res.status_code == 401
