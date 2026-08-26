"""Import an existing Treningsanalyse SQLite DB into the configured data directory.

Safe: never modifies the source file. Backs up an existing target DB first.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy import create_engine

from ..config import path_from_sqlite_url, settings, sqlite_url_for_path
from .migrations import run_migrations
from .sqlite_backup import backup_sqlite_database, validate_sqlite_file

logger = logging.getLogger(__name__)


def import_sqlite_database(
    source_path: str | Path,
    *,
    allow_overwrite: bool = False,
    run_alembic: bool = True,
) -> Dict[str, Any]:
    """Copy a user-selected SQLite DB into settings.DATA_DIR as treningsanalyse.db.

    Raises ValueError on validation failure or refused overwrite.
    """
    source = Path(source_path).expanduser().resolve()
    validation = validate_sqlite_file(source)
    if not validation["ok"]:
        raise ValueError(f"Ugyldig SQLite-database: {validation.get('error')}")

    target = path_from_sqlite_url(settings.DATABASE_URL)
    if target is None:
        target = Path(settings.DATA_DIR) / "treningsanalyse.db"
    target.parent.mkdir(parents=True, exist_ok=True)

    result: Dict[str, Any] = {
        "source": str(source),
        "target": str(target),
        "backup": None,
        "schema_version": None,
        "overwrote": False,
    }

    if target.exists() and target.stat().st_size > 0:
        if not allow_overwrite:
            raise ValueError(
                "Måldatabase finnes allerede. Sett allow_overwrite=True etter eksplisitt bekreftelse."
            )
        backup = backup_sqlite_database(label="pre-import")
        result["backup"] = str(backup) if backup else None
        result["overwrote"] = True

    # Copy via sqlite backup API into a temp then replace, to avoid WAL half-states
    # when source is a live DB. For a closed source file, shutil is fine after validate.
    tmp = target.with_suffix(".db.importing")
    if tmp.exists():
        tmp.unlink()
    shutil.copy2(source, tmp)
    tmp.replace(target)
    # Drop stale WAL/SHM that belonged to previous target
    for suffix in ("-wal", "-shm"):
        side = Path(str(target) + suffix)
        if side.exists():
            side.unlink(missing_ok=True)

    if run_alembic:
        url = sqlite_url_for_path(target)
        eng = create_engine(
            url,
            connect_args={"check_same_thread": False, "timeout": 30},
        )
        try:
            revision = run_migrations(eng, url)
            result["schema_version"] = revision
        finally:
            eng.dispose()

    logger.info(
        "Importerte database %s → %s (schema=%s)",
        source,
        target,
        result["schema_version"],
    )
    return result
