"""add renders.starred for operator feedback

Revision ID: 0002_render_starred
Revises: 0001_initial
Create Date: 2026-04-27

PR 12: track operator star/reject feedback per render so PR 13's
selection_learning can read winning patterns.
  None  = no decision
  True  = starred
  False = rejected
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0002_render_starred"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "renders",
        sa.Column("starred", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("renders", "starred")
