"""Billing service — tier resolution, credit balance, ledger writes.

Phase 3. Stripe integration is intentionally lazy-imported (and gated
on ``STRIPE_SECRET_KEY``) so the api boots cleanly without the SDK
installed for local-only development. The credit ledger and tier
lookup work regardless of Stripe presence — we use them on the free
tier too.

Tier semantics (locked, do not expand without product sign-off):

    free      — 30 credits/month, watermark on output, 1 concurrent
    pro       — 600 credits/month, no watermark, 3 concurrent
    business  — 3000 credits/month, no watermark, 8 concurrent

One render = 1 credit. Future variable pricing (per render-second,
per TTS-second) plugs in here.
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import CreditLedger, Subscription, User


logger = logging.getLogger(__name__)


Tier = Literal["free", "pro", "business"]


@dataclass(frozen=True)
class TierConfig:
    name: Tier
    monthly_credits: int
    watermark: bool
    concurrent_renders: int
    stripe_price_env: Optional[str]   # env var holding the Stripe price ID
    display_name: str


_TIERS: dict[Tier, TierConfig] = {
    "free": TierConfig(
        name="free",
        monthly_credits=30,
        watermark=True,
        concurrent_renders=1,
        stripe_price_env=None,
        display_name="Free",
    ),
    "pro": TierConfig(
        name="pro",
        monthly_credits=600,
        watermark=False,
        concurrent_renders=3,
        stripe_price_env="STRIPE_PRICE_PRO",
        display_name="Pro",
    ),
    "business": TierConfig(
        name="business",
        monthly_credits=3000,
        watermark=False,
        concurrent_renders=8,
        stripe_price_env="STRIPE_PRICE_BUSINESS",
        display_name="Business",
    ),
}


def tier_config(tier: Tier) -> TierConfig:
    return _TIERS[tier]


def all_tiers() -> list[TierConfig]:
    return list(_TIERS.values())


# ─── Tier resolution ────────────────────────────────────────────────────

def get_active_subscription(
    db: Session, user_id: uuid.UUID,
) -> Optional[Subscription]:
    return db.execute(
        select(Subscription)
        .where(
            Subscription.user_id == user_id,
            Subscription.status.in_(("active", "trialing")),
        )
        .order_by(Subscription.updated_at.desc())
    ).scalars().first()


def effective_tier(db: Session, user_id: uuid.UUID) -> Tier:
    sub = get_active_subscription(db, user_id)
    if sub is None or sub.tier not in _TIERS:
        return "free"
    return sub.tier  # type: ignore[return-value]


# ─── Credit ledger ──────────────────────────────────────────────────────

def get_balance(db: Session, user_id: uuid.UUID) -> int:
    """Return the user's current credit balance.

    First-time users get an implicit ``free`` monthly grant lazily on
    first call so the dashboard isn't a depressing zero on signup.
    """
    total = db.execute(
        select(func.coalesce(func.sum(CreditLedger.amount), 0))
        .where(CreditLedger.user_id == user_id)
    ).scalar_one()
    if total == 0 and _user_has_no_ledger(db, user_id):
        _grant_free_starter(db, user_id)
        return _TIERS["free"].monthly_credits
    return int(total)


def _user_has_no_ledger(db: Session, user_id: uuid.UUID) -> bool:
    return db.execute(
        select(func.count(CreditLedger.id))
        .where(CreditLedger.user_id == user_id)
    ).scalar_one() == 0


def _grant_free_starter(db: Session, user_id: uuid.UUID) -> None:
    db.add(CreditLedger(
        user_id=user_id,
        amount=_TIERS["free"].monthly_credits,
        reason="signup_starter_grant",
    ))
    db.commit()


def grant_credits(
    db: Session, user_id: uuid.UUID, amount: int, reason: str,
) -> CreditLedger:
    if amount <= 0:
        raise ValueError("grant amount must be positive")
    entry = CreditLedger(user_id=user_id, amount=amount, reason=reason)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def consume_credits(
    db: Session, user_id: uuid.UUID, amount: int, reason: str,
) -> CreditLedger:
    """Deduct ``amount`` credits. Raises ``InsufficientCredits`` on debt.

    Not atomic against concurrent submits — two simultaneous renders
    *could* both pass the balance check and over-draw. Phase 3 accepts
    that race; Phase 6 will add row-level locking when we add team
    workspaces (where the race is more likely to matter).
    """
    if amount <= 0:
        raise ValueError("consume amount must be positive")
    balance = get_balance(db, user_id)
    if balance < amount:
        raise InsufficientCredits(
            f"need {amount} credits, balance is {balance}"
        )
    entry = CreditLedger(user_id=user_id, amount=-amount, reason=reason)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def refund_credits(
    db: Session, user_id: uuid.UUID, amount: int, reason: str,
) -> CreditLedger:
    """Inverse of :func:`consume_credits` — used when a render fails."""
    return grant_credits(db, user_id, amount, reason)


class InsufficientCredits(Exception):
    """Raised when consume_credits would overdraw the balance."""


# ─── Subscription mutations (called by the Stripe webhook) ──────────────

def upsert_subscription_from_stripe(
    db: Session,
    *,
    user_id: uuid.UUID,
    stripe_customer_id: str,
    stripe_subscription_id: str,
    tier: Tier,
    status: str,
    current_period_end: Optional[datetime],
) -> Subscription:
    """Create or update a Subscription row from Stripe webhook data.

    Idempotent on ``stripe_subscription_id`` so re-delivery of a
    webhook event doesn't create duplicates.
    """
    existing = db.execute(
        select(Subscription)
        .where(Subscription.stripe_subscription_id == stripe_subscription_id)
    ).scalars().first()

    if existing is not None:
        existing.tier = tier
        existing.status = status
        existing.current_period_end = current_period_end
        existing.stripe_customer_id = stripe_customer_id
        db.commit()
        db.refresh(existing)
        return existing

    sub = Subscription(
        user_id=user_id,
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
        tier=tier,
        status=status,
        current_period_end=current_period_end,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


def grant_period_credits(
    db: Session, *, user_id: uuid.UUID, tier: Tier, invoice_id: str,
) -> CreditLedger:
    """Grant the monthly allotment for ``tier``. Idempotent on invoice_id.

    Stripe sends ``invoice.paid`` once per billing cycle — using the
    invoice id as the dedupe key prevents double-grants if the webhook
    is retried.
    """
    existing = db.execute(
        select(CreditLedger)
        .where(CreditLedger.reason == f"stripe_invoice:{invoice_id}")
    ).scalars().first()
    if existing is not None:
        return existing
    return grant_credits(
        db, user_id,
        _TIERS[tier].monthly_credits,
        f"stripe_invoice:{invoice_id}",
    )


# ─── Stripe SDK lazy access ─────────────────────────────────────────────

class StripeUnavailable(RuntimeError):
    """Raised when stripe SDK isn't installed or STRIPE_SECRET_KEY isn't
    set. Routes catch this and return 503 so the failure surfaces
    clearly instead of pretending checkout worked."""


def _get_stripe_module():
    secret = os.environ.get("STRIPE_SECRET_KEY")
    if not secret:
        raise StripeUnavailable("STRIPE_SECRET_KEY not set")
    try:
        import stripe  # type: ignore
    except ImportError as e:
        raise StripeUnavailable(
            "stripe SDK not installed; pip install stripe"
        ) from e
    stripe.api_key = secret
    return stripe


def create_checkout_session(
    *,
    user: User,
    tier: Tier,
    success_url: str,
    cancel_url: str,
) -> str:
    """Create a Stripe Checkout session URL for upgrading to ``tier``."""
    config = _TIERS[tier]
    if not config.stripe_price_env:
        raise ValueError(f"tier '{tier}' is not purchaseable")
    price_id = os.environ.get(config.stripe_price_env)
    if not price_id:
        raise StripeUnavailable(
            f"{config.stripe_price_env} not set — can't start checkout"
        )

    stripe = _get_stripe_module()
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        client_reference_id=str(user.id),
        customer_email=user.email or None,
        metadata={"user_id": str(user.id), "tier": tier},
    )
    return session.url  # type: ignore[no-any-return]


def create_portal_session(
    *, customer_id: str, return_url: str,
) -> str:
    """Create a Stripe Customer Portal session URL."""
    stripe = _get_stripe_module()
    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )
    return session.url  # type: ignore[no-any-return]


def verify_webhook_signature(
    *, payload: bytes, signature_header: str,
) -> dict:
    """Verify a Stripe webhook signature and return the event dict."""
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
    if not secret:
        raise StripeUnavailable("STRIPE_WEBHOOK_SECRET not set")
    stripe = _get_stripe_module()
    event = stripe.Webhook.construct_event(
        payload=payload,
        sig_header=signature_header,
        secret=secret,
    )
    return event  # type: ignore[no-any-return]


# ─── Helpers exposed to the renders router ──────────────────────────────

def render_cost_credits(template: str) -> int:
    """How many credits one render of ``template`` costs.

    Phase 3: flat 1 credit per render. When we add per-second pricing
    in Phase 4 this becomes a function of duration / variant count.
    """
    return 1


def should_watermark(db: Session, user_id: uuid.UUID) -> bool:
    return _TIERS[effective_tier(db, user_id)].watermark
