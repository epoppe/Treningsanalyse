"""Tests for SQLite backup, path helpers, and DB import."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.config import path_from_sqlite_url, sqlite_url_for_path
from app.database.sqlite_backup import backup_sqlite_database, validate_sqlite_file
from app.database.import_database import import_sqlite_database


class SqlitePathHelpersTests(unittest.TestCase):
    def test_roundtrip_unix_style(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "treningsanalyse.db"
            url = sqlite_url_for_path(db)
            self.assertTrue(url.startswith("sqlite:///"))
            parsed = path_from_sqlite_url(url)
            self.assertIsNotNone(parsed)
            self.assertEqual(parsed.resolve(), db.resolve())

    def test_memory_returns_none(self):
        self.assertIsNone(path_from_sqlite_url("sqlite:///:memory:"))


class SqliteBackupTests(unittest.TestCase):
    def _make_db(self, path: Path) -> None:
        conn = sqlite3.connect(str(path))
        conn.execute("CREATE TABLE activities (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO activities (name) VALUES ('run')")
        conn.commit()
        conn.close()

    def test_validate_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "src.db"
            self._make_db(db)
            result = validate_sqlite_file(db)
            self.assertTrue(result["ok"])
            self.assertGreaterEqual(result["tables"], 1)

    def test_backup_and_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "source.db"
            self._make_db(src)
            backup_dir = Path(tmp) / "backups"
            url = sqlite_url_for_path(src)
            dest = backup_sqlite_database(source_url=url, backup_dir=backup_dir, label="test")
            self.assertIsNotNone(dest)
            self.assertTrue(dest.exists())
            self.assertTrue(validate_sqlite_file(dest)["ok"])

            target_root = Path(tmp) / "desktop"
            target_db = target_root / "data" / "treningsanalyse.db"
            target_db.parent.mkdir(parents=True)

            # Patch settings via env for import target
            import os
            from unittest.mock import patch
            from app.config import Settings

            with patch.dict(
                os.environ,
                {
                    "TRAININGSANALYSE_DATA_DIR": str(target_root),
                    "DATABASE_URL": sqlite_url_for_path(target_db),
                },
                clear=False,
            ):
                # import_sqlite_database reads module-level settings — patch it
                import app.database.import_database as imp

                s = Settings(
                    _env_file=None,
                    TRAININGSANALYSE_DATA_DIR=str(target_root),
                    DATABASE_URL=sqlite_url_for_path(target_db),
                )
                with patch.object(imp, "settings", s):
                    result = import_sqlite_database(src, allow_overwrite=False, run_alembic=False)
            self.assertTrue(Path(result["target"]).exists())
            self.assertTrue(validate_sqlite_file(result["target"])["ok"])


if __name__ == "__main__":
    unittest.main()
