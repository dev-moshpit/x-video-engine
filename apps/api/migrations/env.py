"""Alembic environment.

Imports the SaaS API ``Base`` + all models so autogenerate sees the
full metadata. Reads ``DATABASE_URL`` from the environment at runtime
so the same alembic.ini works against local docker, CI, and prod.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make `app` importable when alembic is invoked with `-c apps/api/alembic.ini`
# from any working directory.
_HERE = Path(__file__).resolve().parent          # apps/api/migrations/
_API_ROOT = _HERE.parent                          # apps/api/
sys.path.insert(0, str(_API_ROOT))

from app.db.base import Base  # noqa: E402
from app.db import models  # noqa: E402, F401  — register models with Base


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override sqlalchemy.url from env when set.
db_url = os.environ.get("DATABASE_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
