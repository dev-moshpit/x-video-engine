"""initial schema: users, projects, renders, video_plans, usage

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clerk_user_id", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("tier", sa.String(length=16), nullable=False,
                  server_default="free"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("clerk_user_id"),
    )
    op.create_index("ix_users_clerk_user_id", "users",
                    ["clerk_user_id"], unique=True)

    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("template", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("template_input", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_projects_user_id", "projects", ["user_id"])
    op.create_index("ix_projects_template", "projects", ["template"])

    op.create_table(
        "renders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("stage", sa.String(length=16), nullable=False,
                  server_default="pending"),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
        sa.Column("final_mp4_url", sa.String(length=500), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"],
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id"),
    )
    op.create_index("ix_renders_project_id", "renders", ["project_id"])
    op.create_index("ix_renders_job_id", "renders", ["job_id"], unique=True)

    op.create_table(
        "video_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("render_id", sa.Uuid(), nullable=False),
        sa.Column("plan_json", sa.JSON(), nullable=False),
        sa.Column("score_json", sa.JSON(), nullable=True),
        sa.Column("prompt_hash", sa.String(length=64), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["render_id"], ["renders.id"],
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("render_id"),
    )
    op.create_index("ix_video_plans_render_id", "video_plans",
                    ["render_id"], unique=True)
    op.create_index("ix_video_plans_prompt_hash", "video_plans",
                    ["prompt_hash"])

    op.create_table(
        "usage",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_usage_user_id", "usage", ["user_id"])
    op.create_index("ix_usage_kind", "usage", ["kind"])
    op.create_index("ix_usage_created_at", "usage", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_usage_created_at", table_name="usage")
    op.drop_index("ix_usage_kind", table_name="usage")
    op.drop_index("ix_usage_user_id", table_name="usage")
    op.drop_table("usage")
    op.drop_index("ix_video_plans_prompt_hash", table_name="video_plans")
    op.drop_index("ix_video_plans_render_id", table_name="video_plans")
    op.drop_table("video_plans")
    op.drop_index("ix_renders_job_id", table_name="renders")
    op.drop_index("ix_renders_project_id", table_name="renders")
    op.drop_table("renders")
    op.drop_index("ix_projects_template", table_name="projects")
    op.drop_index("ix_projects_user_id", table_name="projects")
    op.drop_table("projects")
    op.drop_index("ix_users_clerk_user_id", table_name="users")
    op.drop_table("users")
