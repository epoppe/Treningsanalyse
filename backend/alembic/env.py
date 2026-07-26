"""Alembic environment for Treningsanalyse.

Bruker app-konfigurasjon for database-URL og importerer alle modeller
slik at autogenerate ser hele schemaet.

Kan også motta en eksisterende connection via config.attributes['connection']
(brukes ved oppstart mot StaticPool / sqlite:///:memory:).
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from app.config import settings
from app.database.models import Base  # noqa: F401 — importerer alle modeller via __init__

# Alembic Config-objekt
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Alltid bruk app-settings (respekterer DATABASE_URL miljøvariabel / .env)
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

target_metadata = Base.metadata


def _is_sqlite(url: str | None = None) -> bool:
    resolved = url or config.get_main_option("sqlalchemy.url") or ""
    return resolved.startswith("sqlite")


def _configure_context(**kwargs):
    """Felles context-konfigurasjon med SQLite batch-modus."""
    context.configure(
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        # SQLite støtter ikke ALTER TABLE fullt ut — batch rewrite er nødvendig
        render_as_batch=_is_sqlite(),
        **kwargs,
    )


def run_migrations_offline() -> None:
    """Kjør migrasjoner i 'offline'-modus (SQL-script uten live connection)."""
    url = config.get_main_option("sqlalchemy.url")
    _configure_context(
        url=url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Kjør migrasjoner mot en live database-connection.

    Hvis config.attributes['connection'] er satt, gjenbrukes den
    (kritisk for sqlite:///:memory: med StaticPool).

    Merk: SQLAlchemy 2.0 ruller tilbake ved connect()-exit uten commit,
    derfor commit'es eksplisitt etter vellykket migrasjon.
    """
    connection = config.attributes.get("connection")

    if connection is not None:
        if connection.dialect.name == "sqlite":
            connection.execute(text("PRAGMA busy_timeout=30000"))
        _configure_context(
            connection=connection,
            transaction_per_migration=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        # Caller eier connection og commit'er (se app.database.migrations)
        return

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as conn:
        if conn.dialect.name == "sqlite":
            conn.execute(text("PRAGMA busy_timeout=30000"))

        _configure_context(
            connection=conn,
            transaction_per_migration=True,
        )

        with context.begin_transaction():
            context.run_migrations()
        conn.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
