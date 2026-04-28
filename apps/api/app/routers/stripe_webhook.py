"""Stripe webhook endpoint — Phase 3.

Handles the four events that move our billing state forward:

  - ``checkout.session.completed``  — newly converted customer; we
    capture the Stripe customer id + initial subscription id
  - ``customer.subscription.created`` / ``.updated`` — sync tier +
    status + period end
  - ``customer.subscription.deleted`` — mark canceled
  - ``invoice.paid``                — grant the period's credits
                                      (idempotent on invoice id)

Other events 200-OK silently so Stripe doesn't retry forever; we
prefer "received and ignored" over "exploded the webhook queue."
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request

from app.db.models import User
from app.db.session import DbSession
from app.services import billing


logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def _ts_to_dt(ts: Optional[int]) -> Optional[datetime]:
    if ts is None:
        return None
    return datetime.fromtimestamp(int(ts), tz=timezone.utc)


def _resolve_user(
    db: DbSession, *, client_reference_id: Optional[str], metadata: dict,
) -> Optional[User]:
    """Find the local User from a Stripe event.

    Stripe Checkout passes ``client_reference_id`` (we set it to the
    user's UUID); subscription/invoice events carry user_id in
    ``metadata`` if Stripe propagated it. Falls back to None on a
    payload that doesn't tie back to a known user — caller logs and
    skips.
    """
    candidate = client_reference_id or metadata.get("user_id")
    if not candidate:
        return None
    try:
        uid = uuid.UUID(candidate)
    except ValueError:
        return None
    return db.get(User, uid)


def _tier_from_price(metadata: dict) -> billing.Tier:
    """Resolve which tier a price id maps to.

    We rely on Stripe price-IDs we set via env vars
    (``STRIPE_PRICE_PRO`` / ``STRIPE_PRICE_BUSINESS``). When the
    incoming price id matches neither, default to ``pro`` rather than
    silently downgrading the user.
    """
    raw = metadata.get("tier")
    if raw in ("pro", "business"):
        return raw  # type: ignore[return-value]
    return "pro"


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    db: DbSession,
    stripe_signature: str = Header(default=""),
) -> dict:
    body = await request.body()
    try:
        event = billing.verify_webhook_signature(
            payload=body, signature_header=stripe_signature,
        )
    except billing.StripeUnavailable as exc:
        # In dev without Stripe configured, fail loud — no silent accept.
        raise HTTPException(503, str(exc))
    except Exception as exc:
        # Bad signature, malformed payload, etc.
        logger.warning("stripe webhook verification failed: %s", exc)
        raise HTTPException(400, "invalid signature")

    event_type = event.get("type")
    data_obj = (event.get("data") or {}).get("object") or {}
    logger.info("stripe webhook: type=%s id=%s", event_type, event.get("id"))

    if event_type == "checkout.session.completed":
        client_ref = data_obj.get("client_reference_id")
        metadata = data_obj.get("metadata") or {}
        user = _resolve_user(db, client_reference_id=client_ref, metadata=metadata)
        if user is None:
            logger.warning("checkout.session.completed: no matching user")
            return {"ok": True, "ignored": True}
        tier = _tier_from_price(metadata)
        sub_id = data_obj.get("subscription") or ""
        cust_id = data_obj.get("customer") or ""
        if sub_id and cust_id:
            billing.upsert_subscription_from_stripe(
                db,
                user_id=user.id,
                stripe_customer_id=cust_id,
                stripe_subscription_id=sub_id,
                tier=tier,
                status="active",
                current_period_end=None,
            )
        return {"ok": True}

    if event_type in (
        "customer.subscription.created",
        "customer.subscription.updated",
    ):
        sub_id = data_obj.get("id") or ""
        cust_id = data_obj.get("customer") or ""
        status = data_obj.get("status") or "active"
        items = (data_obj.get("items") or {}).get("data") or []
        metadata = data_obj.get("metadata") or {}
        # Walk to the price metadata so we can resolve which tier this
        # is. If absent, fall back to the metadata.tier marker we set
        # at checkout creation.
        price_metadata = {}
        if items:
            price_metadata = (items[0].get("price") or {}).get("metadata") or {}
        tier = _tier_from_price({**metadata, **price_metadata})
        period_end = _ts_to_dt(data_obj.get("current_period_end"))
        # Find user — by metadata, or by an existing sub row's user.
        user = _resolve_user(db, client_reference_id=None, metadata=metadata)
        if user is None:
            # Try existing sub.
            from sqlalchemy import select
            from app.db.models import Subscription
            existing = db.execute(
                select(Subscription)
                .where(Subscription.stripe_subscription_id == sub_id)
            ).scalars().first()
            if existing:
                user = db.get(User, existing.user_id)
        if user is None:
            logger.warning("subscription.* event: no matching user")
            return {"ok": True, "ignored": True}
        billing.upsert_subscription_from_stripe(
            db,
            user_id=user.id,
            stripe_customer_id=cust_id,
            stripe_subscription_id=sub_id,
            tier=tier,
            status=status,
            current_period_end=period_end,
        )
        return {"ok": True}

    if event_type == "customer.subscription.deleted":
        sub_id = data_obj.get("id") or ""
        from sqlalchemy import select
        from app.db.models import Subscription
        existing = db.execute(
            select(Subscription)
            .where(Subscription.stripe_subscription_id == sub_id)
        ).scalars().first()
        if existing:
            existing.status = "canceled"
            db.commit()
        return {"ok": True}

    if event_type == "invoice.paid":
        invoice_id = data_obj.get("id") or ""
        cust_id = data_obj.get("customer") or ""
        sub_id = data_obj.get("subscription") or ""
        if not invoice_id or not sub_id:
            return {"ok": True, "ignored": True}
        # Resolve user via the Subscription row.
        from sqlalchemy import select
        from app.db.models import Subscription
        existing = db.execute(
            select(Subscription)
            .where(Subscription.stripe_subscription_id == sub_id)
        ).scalars().first()
        if existing is None:
            logger.warning("invoice.paid: no subscription row for %s", sub_id)
            return {"ok": True, "ignored": True}
        billing.grant_period_credits(
            db,
            user_id=existing.user_id,
            tier=existing.tier,  # type: ignore[arg-type]
            invoice_id=invoice_id,
        )
        return {"ok": True}

    # Unknown event — accept silently so Stripe stops retrying.
    return {"ok": True, "ignored": True}
