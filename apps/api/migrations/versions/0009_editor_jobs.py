"""add editor_jobs for the single-pass editor (Platform Phase 1)

Revision ID: 0009_editor_jobs
Revises: 0008_clip_jobs
Create Date: 2026-04-29

Backs the new /api/editor endpoints. One row per editor session: the
user uploads, picks trim + aspect + captions, posts to the api, the
worker drains the editor queue and writes ``output_url`` back.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0009_editor_jobs"
down_revision: Union[str, None] = "0008_clip_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "editor_jobs",
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
        sa.Column("trim_start", sa.Float(), nullable=True),
        sa.Column("trim_end", sa.Float(), nullable=True),
        sa.Column(
            "aspect", sa.String(8), nullable=False, server_default="9:16",
        ),
        sa.Column(
            "captions", sa.Boolean(), nullable=False, server_default=sa.true(),
        ),
        sa.Column(
            "caption_language", sa.String(8),
            nullable=False, server_default="auto",
        ),
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
    op.drop_table("editor_jobs")
