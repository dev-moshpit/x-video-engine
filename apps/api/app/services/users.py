"""User-mirror helpers.

Two flows feed the ``users`` table:

1. **Lazy upsert on /api/me** — every authenticated request through
   ``app.main.me`` calls ``upsert_user_from_clerk`` so a row exists by
   the time any other endpoint references the user. This means the
   product works in dev without configuring Clerk webhooks.

2. **Clerk webhook** (``app.routers.webhooks.clerk_webhook``) — pushes
   user.created / user.updated / user.deleted events from Clerk so
   email changes and account deletions are reflected promptly in prod.

Both flows funnel through the same ``upsert_user_from_clerk`` /
``delete_user_by_clerk_id`` helpers in this module to keep the upsert
semantics in one place.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User


def upsert_user_from_clerk(
    db: Session,
    *,
    clerk_user_id: str,
    email: Optional[str] = None,
) -> User:
    """Get-or-create the User row for a Clerk user_id.

    On insert: persists with the provided email and tier="free" (default).
    On existing row: updates the email if a non-null new value is provided
    and differs from the stored value. Other fields are not touched.

    Returns the (possibly fresh) ``User`` instance, attached to ``db``.
    """
    user = db.execute(
        select(User).where(User.clerk_user_id == clerk_user_id)
    ).scalar_one_or_none()

    if user is None:
        user = User(clerk_user_id=clerk_user_id, email=email)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    if email and user.email != email:
        user.email = email
        db.commit()
        db.refresh(user)
    return user


def delete_user_by_clerk_id(db: Session, clerk_user_id: str) -> bool:
    """Hard-delete the User row for a Clerk user_id.

    Returns True if a row was deleted. False if no row matched. Cascades
    to projects / renders / plans / usage via the FK ``ondelete=CASCADE``.
    """
    user = db.execute(
        select(User).where(User.clerk_user_id == clerk_user_id)
    ).scalar_one_or_none()
    if user is None:
        return False
    db.delete(user)
    db.commit()
    return True
