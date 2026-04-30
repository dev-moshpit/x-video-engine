"""add video_generations table — Platform Phase 1

Revision ID: 0010_video_generations
Revises: 0009_editor_jobs
Create Date: 2026-04-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0010_video_generations"
down_revision: Union[str, None] = "0009_editor_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "video_generations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            index=True, nullable=False,
        ),
        sa.Column(
            "job_id", sa.String(64), unique=True, index=True, nullable=False,
        ),
        sa.Column("provider_id", sa.String(32), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("image_url", sa.String(1000), nullable=True),
        sa.Column(
            "duration_seconds", sa.Float(), nullable=False, server_default="4.0",
        ),
        sa.Column("fps", sa.Integer(), nullable=False, server_default="24"),
        sa.Column(
            "aspect_ratio", sa.String(8), nullable=False, server_default="9:16",
        ),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("extra", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "status", sa.String(16), nullable=False, server_default="pending",
        ),
        sa.Column(
            "progress", sa.Float(), nullable=False, server_default="0",
        ),
        sa.Column("output_url", sa.String(1000), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("video_generations")
