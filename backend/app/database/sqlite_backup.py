"""Safe SQLite backup helpers for desktop upgrades and migrations."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from ..config import path_from_sqlite_url, settings

logger = logging.getLogger(__name__)

DEFAULT_RETENTION = 10


def backup_sqlite_database(
    *,
    source_url: Optional[str] = None,
    backup_dir: Optional[str | Path] = None,
    label: str = "backup",
    retention: int = DEFAULT_RETENTION,
) -> Optional[Path]:
    """Create a consistent SQLite backup using the sqlite3 backup API.

    Returns the backup path, or None if the database is not a local SQLite file
    (e.g. :memory: or non-sqlite URL).
    """
    url = source_url or settings.DATABASE_URL
    src_path = path_from_sqlite_url(url)
    if src_path is None:
        logger.info("Skip SQLite backup — DATABASE_URL is not a local SQLite file")
        return None
    if not src_path.exists():
        logger.info("Skip SQLite backup — database file does not exist yet: %s", src_path)
        return None

    dest_root = Path(backup_dir or settings.BACKUP_DIR or (Path(settings.DATA_DIR) / "backups"))
    dest_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    dest = dest_root / f"treningsanalyse-{stamp}-{label}.db"

    src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(str(dest))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()

    logger.info("SQLite backup written to %s", dest)
    _enforce_retention(dest_root, retention=retention)
    return dest


def _enforce_retention(backup_dir: Path, *, retention: int) -> None:
    backups: List[Path] = sorted(
        backup_dir.glob("treningsanalyse-*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in backups[retention:]:
        try:
            old.unlink(missing_ok=True)
            logger.info("Removed old SQLite backup %s", old)
        except OSError as exc:
            logger.warning("Could not remove old backup %s: %s", old, exc)


def validate_sqlite_file(path: Path | str) -> dict:
    """Validate that path is a readable SQLite database. Never modifies the file."""
    candidate = Path(path).expanduser().resolve()
    result = {"ok": False, "path": str(candidate), "error": None, "tables": 0}
    if not candidate.is_file():
        result["error"] = "file_not_found"
        return result
    try:
        conn = sqlite3.connect(f"file:{candidate}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchone()
            result["tables"] = int(row[0]) if row else 0
            # Smoke query
            conn.execute("SELECT 1").fetchone()
            result["ok"] = result["tables"] > 0
            if not result["ok"]:
                result["error"] = "no_tables"
        finally:
            conn.close()
    except sqlite3.Error as exc:
        result["error"] = str(exc)
    return result
