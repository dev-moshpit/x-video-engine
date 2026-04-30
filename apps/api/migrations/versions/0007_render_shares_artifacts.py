"""add render_shares + render_artifacts for Phase 13 / 13.5

Revision ID: 0007_render_shares_artifacts
Revises: 0006_saved_prompts
Create Date: 2026-04-28

Phase 13 — public share preview links for completed renders.
Phase 13.5 — re-exported artifacts (different aspect / captions toggle)
derived from an existing render's final mp4 via FFmpeg.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0007_render_shares_artifacts"
down_revision: Union[str, None] = "0006_saved_prompts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "render_shares",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "render_id",
            sa.Uuid(),
            sa.ForeignKey("renders.id", ondelete="CASCADE"),
            index=True, nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            index=True, nullable=False,
        ),
        sa.Column("token", sa.String(64), unique=True, index=True, nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "render_artifacts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "render_id",
            sa.Uuid(),
            sa.ForeignKey("renders.id", ondelete="CASCADE"),
            index=True, nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("aspect", sa.String(8), nullable=False),
        sa.Column(
            "captions", sa.Boolean(), nullable=False, server_default=sa.true(),
        ),
        sa.Column("url", sa.String(1000), nullable=True),
        sa.Column(
            "status", sa.String(16), nullable=False, server_default="pending",
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("render_artifacts")
    op.drop_table("render_shares")
