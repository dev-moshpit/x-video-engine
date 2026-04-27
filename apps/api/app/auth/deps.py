"""Higher-level auth dependencies that touch the DB.

``current_user`` (auth/clerk.py) returns a ClerkPrincipal — the bearer-
verified Clerk identity. Most endpoints want the mirrored DB ``User``
row instead, so they can FK off ``user.id``. ``current_db_user`` is a
chained dep that does the lazy upsert and returns the row.

This is the same upsert path /api/me uses, so any endpoint that depends
on ``CurrentDbUser`` also keeps the user mirror up-to-date as a side
effect.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.auth.clerk import ClerkPrincipal, current_user
from app.db.models import User
from app.db.session import DbSession
from app.services.users import upsert_user_from_clerk


def current_db_user(
    principal: Annotated[ClerkPrincipal, Depends(current_user)],
    db: DbSession,
) -> User:
    return upsert_user_from_clerk(
        db,
        clerk_user_id=principal.user_id,
        email=principal.email,
    )


CurrentDbUser = Annotated[User, Depends(current_db_user)]
