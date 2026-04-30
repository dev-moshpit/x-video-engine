"""add clip_jobs + clip_artifacts for the AI Clipper (Platform Phase 1)

Revision ID: 0008_clip_jobs
Revises: 0007_render_shares_artifacts
Create Date: 2026-04-29

Backs the new /api/clips/analyze + /api/clips/export endpoints.
``clip_jobs`` holds the analysis run (transcript + scored moments JSON).
``clip_artifacts`` holds each exported short clip the user picked.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0008_clip_jobs"
down_revision: Union[str, None] = "0007_render_shares_artifacts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "clip_jobs",
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
        sa.Column("source_url", sa.String(1000), nullable=False),
        sa.Column(
            "source_kind", sa.String(16), nullable=False, server_default="video",
        ),
        sa.Column(
            "language", sa.String(8), nullable=False, server_default="auto",
        ),
        sa.Column(
            "status", sa.String(16), nullable=False, server_default="pending",
        ),
        sa.Column(
            "progress", sa.Float(), nullable=False, server_default="0",
        ),
        sa.Column("duration_sec", sa.Float(), nullable=True),
        sa.Column("transcript_text", sa.Text(), nullable=True),
        sa.Column("moments", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "clip_artifacts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "clip_job_id",
            sa.Uuid(),
            sa.ForeignKey("clip_jobs.id", ondelete="CASCADE"),
            index=True, nullable=False,
        ),
        sa.Column("moment_id", sa.String(32), nullable=False),
        sa.Column("start_sec", sa.Float(), nullable=False),
        sa.Column("end_sec", sa.Float(), nullable=False),
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
    op.drop_table("clip_artifacts")
    op.drop_table("clip_jobs")
