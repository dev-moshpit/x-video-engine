"""Clerk webhook endpoint.

Clerk sends Svix-signed webhook events on user lifecycle changes.
We verify the signature against ``CLERK_WEBHOOK_SECRET`` and mirror
the relevant events into our ``users`` table:

  user.created   →  upsert_user_from_clerk
  user.updated   →  upsert_user_from_clerk (refreshes email)
  user.deleted   →  delete_user_by_clerk_id (cascades projects etc.)

Other event types (organization.*, session.*, etc.) are accepted
silently with 204 — adding them later is a no-schema-change extension.

Setup steps for prod:
  1. In Clerk dashboard → Webhooks, add endpoint ``${API_BASE_URL}/api/webhooks/clerk``
  2. Subscribe to user.created, user.updated, user.deleted
  3. Copy the signing secret into ``CLERK_WEBHOOK_SECRET``

In dev: not required. The lazy upsert on /api/me keeps the DB in sync
on every authenticated request.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request, Response, status
from svix.webhooks import Webhook, WebhookVerificationError

from app.db.session import DbSession
from app.services.users import (
    delete_user_by_clerk_id,
    upsert_user_from_clerk,
)


router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def _primary_email(data: dict) -> str | None:
    """Pick the primary email from a Clerk user payload, fallback to first."""
    addresses = data.get("email_addresses", []) or []
    if not addresses:
        return None
    primary_id = data.get("primary_email_address_id")
    if primary_id:
        for addr in addresses:
            if addr.get("id") == primary_id:
                return addr.get("email_address")
    return addresses[0].get("email_address")


@router.post(
    "/clerk",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def clerk_webhook(request: Request, db: DbSession) -> Response:
    secret = os.environ.get("CLERK_WEBHOOK_SECRET", "")
    if not secret:
        # Don't 401 — the secret being unset is a config error, not a
        # bad caller. 503 makes that clear in monitoring.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CLERK_WEBHOOK_SECRET is not configured",
        )

    body = await request.body()
    headers = {k: v for k, v in request.headers.items()}

    try:
        event = Webhook(secret).verify(body, headers)
    except WebhookVerificationError as e:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail=f"invalid webhook signature: {e}",
        ) from e

    event_type = event.get("type")
    data = event.get("data", {}) or {}
    clerk_user_id = data.get("id")

    if not clerk_user_id:
        # Malformed payload — accept silently rather than 4xx-loop Clerk.
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    if event_type in ("user.created", "user.updated"):
        upsert_user_from_clerk(
            db,
            clerk_user_id=clerk_user_id,
            email=_primary_email(data),
        )
    elif event_type == "user.deleted":
        delete_user_by_clerk_id(db, clerk_user_id)
    # Any other event type is acknowledged and ignored.

    return Response(status_code=status.HTTP_204_NO_CONTENT)
