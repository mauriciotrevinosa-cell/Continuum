"""Alembic environment.

The URL is read from Continuum settings rather than alembic.ini so that no
database password is ever written into a committed file (ADR-0004 section 9).
"""

from __future__ import annotations

from alembic import context
from continuum_config import get_settings
from continuum_db.models import Base
from sqlalchemy import engine_from_config, pool

config = context.config
target_metadata = Base.metadata

config.set_main_option(
    "sqlalchemy.url",
    get_settings().database_url.get_secret_value().replace("%", "%%"),
)


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
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
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
