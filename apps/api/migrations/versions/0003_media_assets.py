"""add media_assets table for the Phase 2.5 media library

Revision ID: 0003_media_assets
Revises: 0002_render_starred
Create Date: 2026-04-28

Phase 2.5: per-user media library. Stores assets the operator saved
from Pexels/Pixabay or uploaded directly so they can attach the same
clip to multiple projects without re-fetching.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0003_media_assets"
down_revision: Union[str, None] = "0002_render_starred"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "media_assets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            index=True, nullable=False,
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_asset_id", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),  # video|image
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("thumbnail_url", sa.String(1000), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration_sec", sa.Float(), nullable=True),
        sa.Column("orientation", sa.String(16), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("attribution", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_media_assets_provider_asset",
        "media_assets",
        ["provider", "provider_asset_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_media_assets_provider_asset", table_name="media_assets")
    op.drop_table("media_assets")
