"""Hjelpefunksjoner for Alembic-migrasjoner.

Erstatter tidligere manuell create_all() + migrate_* ved oppstart.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import Connection, Engine

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


def get_alembic_config(database_url: Optional[str] = None) -> Config:
    """Bygg Alembic Config pekt mot prosjektets alembic.ini."""
    if not ALEMBIC_INI.exists():
        raise FileNotFoundError(f"Finner ikke alembic.ini: {ALEMBIC_INI}")

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    if database_url:
        cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def get_current_revision(engine: Engine) -> Optional[str]:
    """Returner gjeldende schema-revisjon, eller None hvis ikke migrert."""
    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        return context.get_current_revision()


def get_head_revision(database_url: Optional[str] = None) -> Optional[str]:
    """Returner head-revisjon fra migrasjonsskriptene."""
    cfg = get_alembic_config(database_url)
    script = ScriptDirectory.from_config(cfg)
    return script.get_current_head()


def get_all_heads(database_url: Optional[str] = None) -> list[str]:
    """Alle Alembic heads — mer enn én er en CI-feil."""
    cfg = get_alembic_config(database_url)
    script = ScriptDirectory.from_config(cfg)
    return list(script.get_heads())


def assert_single_alembic_head(database_url: Optional[str] = None) -> str:
    heads = get_all_heads(database_url)
    if len(heads) != 1:
        raise RuntimeError(f"Expected exactly one Alembic head, found {heads}")
    return heads[0]


def _has_application_tables(connection: Connection) -> bool:
    """True hvis databasen allerede har app-tabeller (pre-Alembic DB)."""
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    # 'activities' er kjernetabellen — finnes den, er DB opprettet manuelt tidligere
    return "activities" in tables


def _stamp_head_if_legacy(connection: Connection, cfg: Config) -> bool:
    """Stemple head på eksisterende DB uten alembic_version (uten datatap).

    Returnerer True hvis stamp ble utført.
    """
    context = MigrationContext.configure(connection)
    if context.get_current_revision() is not None:
        return False

    if not _has_application_tables(connection):
        return False

    script = ScriptDirectory.from_config(cfg)
    head = script.get_current_head()
    if head is None:
        logger.warning("Ingen Alembic head-revisjon funnet — hopper over stamp.")
        return False

    logger.info(
        "Eksisterende database uten alembic_version funnet. "
        "Stempler schema til head (%s) uten å endre data.",
        head,
    )
    # Stamp via samme connection
    cfg.attributes["connection"] = connection
    command.stamp(cfg, "head")
    return True


def run_migrations(engine: Engine, database_url: str) -> str:
    """Kjør alembic upgrade head på den gitte engine.

    For eksisterende databaser opprettet med create_all/migrate_*:
    stemples head først (schema antas å matche modellene), deretter upgrade.

    Gjenbruker engine-connection slik at sqlite:///:memory: med StaticPool fungerer.

    Returnerer gjeldende revisjon etter kjøring.
    """
    cfg = get_alembic_config(database_url)

    with engine.connect() as connection:
        _stamp_head_if_legacy(connection, cfg)
        cfg.attributes["connection"] = connection
        logger.info("Kjører alembic upgrade head...")
        command.upgrade(cfg, "head")
        connection.commit()

    revision = get_current_revision(engine)
    if revision is None:
        raise RuntimeError("Alembic upgrade fullførte, men ingen revisjon ble satt.")

    logger.info("Database-schema er på revisjon %s", revision)
    return revision


def get_schema_version(engine: Engine) -> dict:
    """Hent schema-versjon for health check."""
    try:
        current = get_current_revision(engine)
        head = get_head_revision()
        at_head = current is not None and current == head
        return {
            "schema_version": current,
            "schema_head": head,
            "schema_at_head": at_head,
        }
    except Exception as exc:
        logger.warning("Kunne ikke hente schema-versjon: %s", exc)
        return {
            "schema_version": None,
            "schema_head": None,
            "schema_at_head": False,
            "error": str(exc),
        }
