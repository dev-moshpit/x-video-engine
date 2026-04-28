"""add subscriptions + credits_ledger for Phase 3 billing

Revision ID: 0004_billing
Revises: 0003_media_assets
Create Date: 2026-04-28

Phase 3: Stripe-backed subscriptions + a credits ledger that gates
render submissions. We deliberately do NOT bake "tier" onto the user
row — a user has at most one *active* subscription, looked up via
``subscriptions.user_id + status='active'``. Tier-derived behavior
(watermark, monthly grant, concurrency limits) is computed from the
subscription, not from a denormalized column, so a webhook update
takes effect immediately without a second write.

The credits_ledger is append-only: every grant (monthly refill, manual
top-up) and every consume (render submitted) is one row. Balance =
SUM(amount). Safer to audit than a mutable counter.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0004_billing"
down_revision: Union[str, None] = "0003_media_assets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            index=True, nullable=False,
        ),
        sa.Column("stripe_customer_id", sa.String(64), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(64), nullable=True),
        sa.Column("tier", sa.String(16), nullable=False, server_default="free"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index(
        "ix_subscriptions_stripe_sub",
        "subscriptions",
        ["stripe_subscription_id"],
        unique=True,
    )

    op.create_table(
        "credits_ledger",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            index=True, nullable=False,
        ),
        # Positive grants, negative consumes.
        sa.Column("amount", sa.Integer(), nullable=False),
        # Free-form: "monthly_grant", "render_consume:<job_id>", "topup",
        # "stripe_invoice:<invoice_id>", "manual_adjust".
        sa.Column("reason", sa.String(120), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            index=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("credits_ledger")
    op.drop_index("ix_subscriptions_stripe_sub", table_name="subscriptions")
    op.drop_table("subscriptions")
