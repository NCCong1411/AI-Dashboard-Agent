"""Alembic environment using only the migration credential."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool

from app.config import get_settings
from app.db.connections import require_migration_ready
from app.db.migration_safety import (
    include_owned_name,
    include_owned_object,
    reject_injected_connection,
)
from app.db.models import Base


config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def migration_url() -> str:
    settings = get_settings()
    return require_migration_ready(settings).render_as_string(hide_password=False)


def run_migrations_offline() -> None:
    context.configure(
        url=migration_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        include_name=include_owned_name,
        include_object=include_owned_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy import engine_from_config

    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = migration_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_name=include_owned_name,
            include_object=include_owned_object,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


reject_injected_connection(config.attributes.get("connection"))

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
