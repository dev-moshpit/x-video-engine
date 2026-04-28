"""Billing endpoint tests — Phase 3.

Coverage:
  - GET  /api/billing/tiers      catalog
  - GET  /api/billing            status (free user gets starter grant)
  - POST /api/billing/checkout   503 when Stripe not configured
  - render submit consumes credits
  - render submit returns 402 when balance is exhausted
  - subscription upsert sets tier
  - period grant is idempotent on invoice id
"""

from __future__ import annotations

import fakeredis
import pytest
from fastapi.testclient import TestClient

from app.auth.clerk import ClerkPrincipal, current_user
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.services import billing, queue as queue_module


def _principal(uid: str) -> ClerkPrincipal:
    return ClerkPrincipal(user_id=uid, session_id="s", email=f"{uid}@x.com")


@pytest.fixture(autouse=True)
def fresh_schema_and_queue():
    Base.metadata.create_all(engine)
    queue_module.set_redis(fakeredis.FakeRedis(decode_responses=True))
    yield
    queue_module.set_redis(None)
    Base.metadata.drop_all(engine)


@pytest.fixture
def client():
    app.dependency_overrides[current_user] = lambda: _principal("user_alice")
    yield TestClient(app)
    app.dependency_overrides.pop(current_user, None)


# ─── Catalog ────────────────────────────────────────────────────────────

def test_tiers_catalog_returns_three(client: TestClient):
    res = client.get("/api/billing/tiers")
    assert res.status_code == 200
    body = res.json()
    names = sorted(t["name"] for t in body)
    assert names == ["business", "free", "pro"]
    free = next(t for t in body if t["name"] == "free")
    assert free["watermark"] is True
    assert free["monthly_credits"] == 30


# ─── Status + starter grant ─────────────────────────────────────────────

def test_first_status_call_grants_free_starter(client: TestClient):
    res = client.get("/api/billing")
    assert res.status_code == 200
    body = res.json()
    assert body["tier"] == "free"
    assert body["balance"] == 30
    assert body["watermark"] is True
    assert body["has_active_subscription"] is False


def test_starter_grant_is_idempotent(client: TestClient):
    """Calling status twice doesn't double-grant."""
    client.get("/api/billing")
    res = client.get("/api/billing")
    assert res.json()["balance"] == 30


# ─── Stripe surface ─────────────────────────────────────────────────────

def test_checkout_returns_503_without_stripe(client: TestClient, monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    res = client.post(
        "/api/billing/checkout",
        json={
            "tier": "pro",
            "success_url": "https://example.invalid/ok",
            "cancel_url": "https://example.invalid/cancel",
        },
    )
    assert res.status_code == 503


def test_portal_requires_active_subscription(client: TestClient):
    # No sub yet — portal call should reject.
    res = client.post(
        "/api/billing/portal",
        json={"return_url": "https://example.invalid/back"},
    )
    assert res.status_code == 400


# ─── Credits + render gate ──────────────────────────────────────────────

def _create_project_and_render(client: TestClient) -> tuple[str, int]:
    pid = client.post(
        "/api/projects",
        json={
            "template": "voiceover",
            "name": "test",
            "template_input": {
                "script": "Test script for credit-gated render.",
                "background_color": "#0b0b0f",
                "caption_style": "bold_word",
                "aspect": "9:16",
            },
        },
    ).json()["id"]
    res = client.post(f"/api/projects/{pid}/render")
    return pid, res.status_code


def test_render_consumes_one_credit(client: TestClient):
    # Trigger starter grant.
    assert client.get("/api/billing").json()["balance"] == 30

    _pid, status_code = _create_project_and_render(client)
    assert status_code == 202
    after = client.get("/api/billing").json()
    assert after["balance"] == 29


def test_render_returns_402_when_balance_exhausted(client: TestClient):
    # Drain the balance via the service layer.
    from app.db.models import User
    db = SessionLocal()
    try:
        db_user = db.query(User).filter(User.clerk_user_id == "user_alice").first()
        # First call seeds the starter grant via balance lookup.
        billing.get_balance(db, db_user.id) if db_user else None
        # The balance lookup might have been triggered before the user
        # exists — make sure the user is created first by hitting /api/me.
    finally:
        db.close()

    client.get("/api/me")
    db = SessionLocal()
    try:
        db_user = db.query(User).filter(User.clerk_user_id == "user_alice").first()
        billing.get_balance(db, db_user.id)
        # Drain by consuming everything.
        bal = billing.get_balance(db, db_user.id)
        if bal > 0:
            billing.consume_credits(db, db_user.id, bal, "test_drain")
    finally:
        db.close()

    _pid, status_code = _create_project_and_render(client)
    assert status_code == 402


# ─── Subscription mutations (service-layer) ─────────────────────────────

def test_upsert_subscription_sets_active_tier_and_idempotent(client: TestClient):
    """Two webhook deliveries for the same subscription_id must not
    create two subscription rows."""
    client.get("/api/me")  # ensure user exists

    from app.db.models import Subscription, User

    db = SessionLocal()
    try:
        db_user = db.query(User).filter(User.clerk_user_id == "user_alice").one()
        billing.upsert_subscription_from_stripe(
            db,
            user_id=db_user.id,
            stripe_customer_id="cus_test",
            stripe_subscription_id="sub_test",
            tier="pro",
            status="active",
            current_period_end=None,
        )
        billing.upsert_subscription_from_stripe(
            db,
            user_id=db_user.id,
            stripe_customer_id="cus_test",
            stripe_subscription_id="sub_test",
            tier="pro",
            status="active",
            current_period_end=None,
        )
        rows = db.query(Subscription).filter_by(user_id=db_user.id).all()
        assert len(rows) == 1
        assert billing.effective_tier(db, db_user.id) == "pro"
    finally:
        db.close()


def test_period_grant_is_idempotent_on_invoice_id(client: TestClient):
    client.get("/api/me")

    from app.db.models import User
    db = SessionLocal()
    try:
        db_user = db.query(User).filter(User.clerk_user_id == "user_alice").one()
        # Establish baseline via starter grant.
        baseline = billing.get_balance(db, db_user.id)

        billing.grant_period_credits(
            db, user_id=db_user.id, tier="pro", invoice_id="inv_001",
        )
        billing.grant_period_credits(
            db, user_id=db_user.id, tier="pro", invoice_id="inv_001",
        )
        # Pro grants 600 credits — only ONCE despite two calls.
        assert billing.get_balance(db, db_user.id) == baseline + 600
    finally:
        db.close()


# ─── Stripe webhook surface ─────────────────────────────────────────────

def test_webhook_returns_503_when_stripe_missing(client: TestClient, monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    res = client.post(
        "/api/webhooks/stripe",
        content=b"{}",
        headers={"stripe-signature": "fake"},
    )
    assert res.status_code == 503
