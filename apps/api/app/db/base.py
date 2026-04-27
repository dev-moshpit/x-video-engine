"""Declarative base for SQLAlchemy 2.0 ORM models.

Models live in ``app.db.models`` and inherit from ``Base``. Alembic's
``env.py`` imports ``Base`` plus ``models`` so autogenerate sees the
full metadata.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
