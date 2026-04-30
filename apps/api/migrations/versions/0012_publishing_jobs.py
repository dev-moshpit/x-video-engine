"""add publishing_jobs table — Platform Phase 1

Revision ID: 0012_publishing_jobs
Revises: 0011_presenter_jobs
Create Date: 2026-04-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0012_publishing_jobs"
down_revision: Union[str, None] = "0011_presenter_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "publishing_jobs",
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
        sa.Column("video_url", sa.String(1000), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "privacy", sa.String(16), nullable=False, server_default="private",
        ),
        sa.Column(
            "status", sa.String(16), nullable=False, server_default="pending",
        ),
        sa.Column("external_id", sa.String(128), nullable=True),
        sa.Column("external_url", sa.String(1000), nullable=True),
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
    op.drop_table("publishing_jobs")
