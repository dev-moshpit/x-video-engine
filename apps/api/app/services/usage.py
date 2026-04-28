"""Usage aggregation (PR 11).

Reads from the ``usage`` table written by the worker and returns a
``{kind: total_value}`` dict for one user. Cheap GROUP BY query —
indexed on ``(user_id, kind)`` via the per-column indexes on the
``usage`` table.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Usage


def aggregate_user_usage(db: Session, user_id: uuid.UUID) -> dict[str, float]:
    """Return ``{kind: SUM(value)}`` for the user across all time."""
    rows = db.execute(
        select(Usage.kind, func.sum(Usage.value))
        .where(Usage.user_id == user_id)
        .group_by(Usage.kind)
    ).all()
    return {kind: float(total or 0.0) for kind, total in rows}
