from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool, text

from alembic import context
from app.db.base import Base
from app.models import entities  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    return os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url"))


def ensure_wide_version_table(connection) -> None:
    """Allow descriptive revision ids longer than Alembic's default 32 chars."""
    if connection.dialect.name == "postgresql":
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS alembic_version (
                  version_num VARCHAR(128) NOT NULL PRIMARY KEY
                )
                """
            )
        )
        connection.execute(text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)"))


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        ensure_wide_version_table(connection)
        if connection.in_transaction():
            connection.commit()
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
