"""add presenter_jobs table — Platform Phase 1

Revision ID: 0011_presenter_jobs
Revises: 0010_video_generations
Create Date: 2026-04-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0011_presenter_jobs"
down_revision: Union[str, None] = "0010_video_generations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "presenter_jobs",
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
        sa.Column("script", sa.Text(), nullable=False),
        sa.Column("avatar_image_url", sa.String(1000), nullable=False),
        sa.Column("voice", sa.String(64), nullable=True),
        sa.Column(
            "voice_rate", sa.String(8), nullable=False, server_default="+0%",
        ),
        sa.Column(
            "aspect_ratio", sa.String(8), nullable=False, server_default="9:16",
        ),
        sa.Column("headline", sa.String(200), nullable=True),
        sa.Column("ticker", sa.String(400), nullable=True),
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
    op.drop_table("presenter_jobs")
