"""Billing endpoints — Phase 3.

Surface:

  GET  /api/billing               — current tier + balance + sub info
  GET  /api/billing/tiers         — public catalog of plans (no auth)
  POST /api/billing/checkout      — start a Stripe Checkout session
  POST /api/billing/portal        — open the Stripe customer portal

The webhook lives in :mod:`app.routers.stripe_webhook` because it has
its own signature-verification and JSON-parsing flow that doesn't fit
the rest of this router.
"""

from __future__ import annotations

import logging
import os
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.auth.deps import CurrentDbUser
from app.db.session import DbSession
from app.services import billing


logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/billing", tags=["billing"])


# ─── /api/billing/tiers (public) ────────────────────────────────────────

class TierInfo(BaseModel):
    name: str
    display_name: str
    monthly_credits: int
    watermark: bool
    concurrent_renders: int
    purchaseable: bool


@router.get("/tiers", response_model=list[TierInfo])
def list_tiers() -> list[TierInfo]:
    return [
        TierInfo(
            name=t.name,
            display_name=t.display_name,
            monthly_credits=t.monthly_credits,
            watermark=t.watermark,
            concurrent_renders=t.concurrent_renders,
            purchaseable=bool(
                t.stripe_price_env and os.environ.get(t.stripe_price_env)
            ),
        )
        for t in billing.all_tiers()
    ]


# ─── /api/billing (status) ──────────────────────────────────────────────

class BillingStatus(BaseModel):
    tier: str
    balance: int
    monthly_credits: int
    watermark: bool
    has_active_subscription: bool
    stripe_customer_id: Optional[str]
    current_period_end: Optional[str]


@router.get("", response_model=BillingStatus)
def get_status(user: CurrentDbUser, db: DbSession) -> BillingStatus:
    sub = billing.get_active_subscription(db, user.id)
    tier = billing.effective_tier(db, user.id)
    cfg = billing.tier_config(tier)
    return BillingStatus(
        tier=tier,
        balance=billing.get_balance(db, user.id),
        monthly_credits=cfg.monthly_credits,
        watermark=cfg.watermark,
        has_active_subscription=sub is not None,
        stripe_customer_id=(sub.stripe_customer_id if sub else None),
        current_period_end=(
            sub.current_period_end.isoformat()
            if sub and sub.current_period_end else None
        ),
    )


# ─── /api/billing/checkout ──────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    tier: Literal["pro", "business"]
    success_url: str
    cancel_url: str


class CheckoutResponse(BaseModel):
    url: str


@router.post("/checkout", response_model=CheckoutResponse)
def create_checkout(
    body: CheckoutRequest, user: CurrentDbUser, db: DbSession,
) -> CheckoutResponse:
    try:
        url = billing.create_checkout_session(
            user=user,
            tier=body.tier,
            success_url=body.success_url,
            cancel_url=body.cancel_url,
        )
    except billing.StripeUnavailable as exc:
        raise HTTPException(503, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return CheckoutResponse(url=url)


# ─── /api/billing/portal ────────────────────────────────────────────────

class PortalRequest(BaseModel):
    return_url: str


@router.post("/portal", response_model=CheckoutResponse)
def create_portal(
    body: PortalRequest, user: CurrentDbUser, db: DbSession,
) -> CheckoutResponse:
    sub = billing.get_active_subscription(db, user.id)
    if sub is None or not sub.stripe_customer_id:
        raise HTTPException(
            400, "no active subscription — upgrade first via /checkout"
        )
    try:
        url = billing.create_portal_session(
            customer_id=sub.stripe_customer_id,
            return_url=body.return_url,
        )
    except billing.StripeUnavailable as exc:
        raise HTTPException(503, str(exc))
    return CheckoutResponse(url=url)
