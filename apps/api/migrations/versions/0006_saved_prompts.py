"""add saved_prompts for Phase 9

Revision ID: 0006_saved_prompts
Revises: 0005_brand_kits
Create Date: 2026-04-28

Phase 9 — retention loop. Lets the operator save reusable prompt
configurations per template (presets) and surfaces "your most-used
prompt" on the dashboard.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0006_saved_prompts"
down_revision: Union[str, None] = "0005_brand_kits"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "saved_prompts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            index=True, nullable=False,
        ),
        sa.Column("template", sa.String(32), index=True, nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("template_input", sa.JSON(), nullable=False),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
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
    op.drop_table("saved_prompts")
