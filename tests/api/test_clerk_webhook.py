"""Clerk webhook handler tests (PR 3).

Three paths exercised:
  1. Bad signature → 401
  2. Valid user.created event → row inserted in users table
  3. Valid user.deleted event → row removed
"""

from __future__ import annotations

import json
import os
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from svix.webhooks import Webhook

from app.db.base import Base
from app.db.models import User
from app.db.session import SessionLocal, engine
from app.main import app


@pytest.fixture(autouse=True)
def fresh_schema():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client():
    return TestClient(app)


def _sign(secret: str, body: dict) -> tuple[bytes, dict[str, str]]:
    """Produce a Svix-signed (body, headers) pair for the test client."""
    raw = json.dumps(body).encode("utf-8")
    msg_id = "msg_test_" + str(int(time.time() * 1000))
    timestamp = str(int(time.time()))
    sig = Webhook(secret).sign(msg_id, int(timestamp), raw.decode("utf-8"))
    headers = {
        "svix-id": msg_id,
        "svix-timestamp": timestamp,
        "svix-signature": sig,
        "content-type": "application/json",
    }
    return raw, headers


def test_invalid_signature_returns_401(client: TestClient):
    body = {"type": "user.created", "data": {"id": "user_x"}}
    raw = json.dumps(body).encode("utf-8")
    headers = {
        "svix-id": "msg_test_bad",
        "svix-timestamp": str(int(time.time())),
        "svix-signature": "v1,not-a-real-signature",
        "content-type": "application/json",
    }
    res = client.post("/api/webhooks/clerk", content=raw, headers=headers)
    assert res.status_code == 401


def test_user_created_event_inserts_user(client: TestClient):
    secret = os.environ["CLERK_WEBHOOK_SECRET"]
    body = {
        "type": "user.created",
        "data": {
            "id": "user_clerk_abc",
            "email_addresses": [
                {"id": "em_1", "email_address": "alice@example.com"},
                {"id": "em_2", "email_address": "alice+work@example.com"},
            ],
            "primary_email_address_id": "em_1",
        },
    }
    raw, headers = _sign(secret, body)
    res = client.post("/api/webhooks/clerk", content=raw, headers=headers)
    assert res.status_code == 204

    db = SessionLocal()
    try:
        row = db.execute(
            select(User).where(User.clerk_user_id == "user_clerk_abc")
        ).scalar_one_or_none()
    finally:
        db.close()
    assert row is not None
    assert row.email == "alice@example.com"


def test_user_deleted_event_removes_user(client: TestClient):
    secret = os.environ["CLERK_WEBHOOK_SECRET"]

    # Seed a user, then send the delete event.
    db = SessionLocal()
    db.add(User(clerk_user_id="user_to_delete", email="bye@example.com"))
    db.commit()
    db.close()

    body = {
        "type": "user.deleted",
        "data": {"id": "user_to_delete"},
    }
    raw, headers = _sign(secret, body)
    res = client.post("/api/webhooks/clerk", content=raw, headers=headers)
    assert res.status_code == 204

    db = SessionLocal()
    try:
        row = db.execute(
            select(User).where(User.clerk_user_id == "user_to_delete")
        ).scalar_one_or_none()
    finally:
        db.close()
    assert row is None


def test_unknown_event_type_is_204_noop(client: TestClient):
    secret = os.environ["CLERK_WEBHOOK_SECRET"]
    body = {"type": "organization.created", "data": {"id": "org_x"}}
    raw, headers = _sign(secret, body)
    res = client.post("/api/webhooks/clerk", content=raw, headers=headers)
    assert res.status_code == 204
