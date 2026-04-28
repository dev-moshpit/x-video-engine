"""add brand_kits for Phase 6

Revision ID: 0005_brand_kits
Revises: 0004_billing
Create Date: 2026-04-28

Phase 6 — light brand-kit support. One row per user; the operator's
brand color + accent + (optional) logo URL get applied to color-aware
templates (top_five, would_you_rather, twitter, fake_text). No team
support yet — workspaces are explicitly deferred.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0005_brand_kits"
down_revision: Union[str, None] = "0004_billing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "brand_kits",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            unique=True, index=True, nullable=False,
        ),
        sa.Column("brand_color", sa.String(7), nullable=True),
        sa.Column("accent_color", sa.String(7), nullable=True),
        sa.Column("text_color", sa.String(7), nullable=True),
        sa.Column("logo_url", sa.String(1000), nullable=True),
        sa.Column("brand_name", sa.String(120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("brand_kits")
