"""Alembic migration environment.

Unlike a vanilla Alembic setup, the database URL comes from Tank's
:class:`AppConfig` — **not** ``sqlalchemy.url`` in ``alembic.ini``.
This guarantees a single source of truth: wherever ``config.yaml``
points, migrations go.

Usage (from ``backend/core``)::

    uv run alembic -c src/tank_backend/persistence/migrations/alembic.ini upgrade head

Or programmatically via :func:`tank_backend.persistence.migrate.run_migrations`.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import every model module so their tables are registered on Base.metadata
# before --autogenerate compares against the live DB.
from tank_backend.persistence.base import Base
from tank_backend.persistence.models import (  # noqa: F401 — side-effect import
    ChannelReadStateRow,
    ChannelRow,
    ConnectorIdentityRow,
    ConversationRow,
    EmbeddingRow,
    JobRow,
    JobRunRow,
    SpeakerRow,
)

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers=False: fileConfig() otherwise nukes every
    # logger that was already configured, which silently breaks caplog in
    # tests that run after a migration.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _resolve_url() -> str:
    """Resolve the DB URL.

    Priority:
      1. ``-x url=...`` on the Alembic command line (test harness, CLI override).
      2. ``sqlalchemy.url`` in alembic.ini (we leave this blank by default).
      3. ``AppConfig.database.url`` — the production path.
    """
    x_args = context.get_x_argument(as_dictionary=True)
    if x_args.get("url"):
        return x_args["url"]

    ini_url = config.get_main_option("sqlalchemy.url")
    if ini_url:
        return ini_url

    from tank_backend.config import AppConfig, find_config_yaml
    from tank_backend.persistence.database import _expand_sqlite_url

    app_config = AppConfig.load(find_config_yaml())
    return _expand_sqlite_url(app_config.database.url)


def run_migrations_offline() -> None:
    """Generate SQL without connecting to a database (``alembic upgrade --sql``)."""
    url = _resolve_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=url.startswith("sqlite"),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations against a live database connection."""
    url = _resolve_url()

    connectable = engine_from_config(
        {"sqlalchemy.url": url},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=url.startswith("sqlite"),
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
