"""Regression: packaged/read-only install must never write under BACKEND_DIR."""

from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def _is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


class PackagedReadonlyConfigTests(unittest.TestCase):
    def test_settings_resolves_appdata_without_writing_package(self):
        """Read-only package tree + AppData root — no mutable writes under package."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            package = tmp_path / "Program Files" / "Treningsanalyse" / "resources" / "backend"
            package.mkdir(parents=True)
            appdata = tmp_path / "AppData" / "Treningsanalyse"

            pkg_token = str((package / "tokens").absolute())
            pkg_data = str((package / "data").absolute())
            import app.config as config_mod

            pkg_db = config_mod.sqlite_url_for_path(package / "data" / "treningsanalyse.db")

            # Simulate Program Files: package is not writable
            package.chmod(stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP)
            try:
                config_mod.reset_settings_cache()
                with patch.object(config_mod, "BACKEND_DIR", package), patch.object(
                    config_mod, "DEFAULT_DATA_DIR", package / "data"
                ), patch.object(config_mod, "DEFAULT_TOKEN_DIR", pkg_token), patch.object(
                    config_mod, "DEFAULT_DATABASE_URL", pkg_db
                ):
                    # Would raise PermissionError if Settings still mkdir()'d under package
                    s = config_mod.Settings(
                        _env_file=None,
                        DESKTOP_MODE=True,
                        TRAININGSANALYSE_DATA_DIR=str(appdata),
                        TOKEN_DIR=pkg_token,
                        DATA_DIR=pkg_data,
                        DATABASE_URL=pkg_db,
                    )

                    self.assertFalse((package / "tokens").exists())
                    self.assertFalse((package / "data").exists())
                    self.assertFalse((package / "logs").exists())

                    expected = appdata.expanduser().resolve()
                    self.assertEqual(Path(s.TOKEN_DIR).resolve(), (expected / "tokens").resolve())
                    self.assertEqual(Path(s.DATA_DIR).resolve(), (expected / "data").resolve())
                    self.assertEqual(Path(s.FIT_DATA_DIR).resolve(), (expected / "fit").resolve())
                    self.assertEqual(Path(s.CACHE_DIR).resolve(), (expected / "cache").resolve())
                    self.assertEqual(Path(s.LOG_DIR).resolve(), (expected / "logs").resolve())
                    self.assertEqual(Path(s.BACKUP_DIR).resolve(), (expected / "backups").resolve())
                    self.assertEqual(Path(s.EXPORT_DIR).resolve(), (expected / "exports").resolve())
                    self.assertIn("treningsanalyse.db", s.DATABASE_URL)
                    db_path = config_mod.path_from_sqlite_url(s.DATABASE_URL)
                    self.assertIsNotNone(db_path)
                    assert db_path is not None
                    self.assertTrue(_is_under(db_path, expected / "data"))

                    self.assertTrue(Path(s.TOKEN_DIR).is_dir())
                    self.assertTrue(Path(s.DATA_DIR).is_dir())
                    self.assertTrue(Path(s.FIT_DATA_DIR).is_dir())
                    self.assertTrue(Path(s.CACHE_DIR).is_dir())
                    self.assertTrue(Path(s.LOG_DIR).is_dir())
                    self.assertTrue(Path(s.BACKUP_DIR).is_dir())
                    self.assertTrue(Path(s.EXPORT_DIR).is_dir())
            finally:
                try:
                    package.chmod(stat.S_IRWXU)
                except OSError:
                    pass

    def test_desktop_mode_requires_data_dir(self):
        import app.config as config_mod

        config_mod.reset_settings_cache()
        with self.assertRaises(RuntimeError):
            config_mod.Settings(_env_file=None, DESKTOP_MODE=True, TRAININGSANALYSE_DATA_DIR=None)

    def test_module_import_does_not_eagerly_bind_settings(self):
        import app.config as config_mod

        self.assertTrue(callable(getattr(config_mod, "__getattr__", None)))
        self.assertNotIn("settings", config_mod.__dict__)

    def test_importing_config_with_desktop_env_leaves_package_clean(self):
        """Accessing settings with AppData env must not create BACKEND_DIR/tokens."""
        with tempfile.TemporaryDirectory() as tmp:
            appdata = Path(tmp) / "appdata"
            import app.config as config_mod

            backend_tokens = config_mod.BACKEND_DIR / "tokens"
            before = backend_tokens.exists()
            config_mod.reset_settings_cache()
            with patch.dict(
                os.environ,
                {
                    "TRAININGSANALYSE_DATA_DIR": str(appdata),
                    "DESKTOP_MODE": "true",
                    "SKIP_GARMIN_INIT": "true",
                },
                clear=False,
            ):
                s = config_mod.get_settings()
                self.assertTrue(str(s.TOKEN_DIR).startswith(str(appdata.resolve())) or
                                Path(s.TOKEN_DIR).resolve() == (appdata.resolve() / "tokens"))
            # Did not newly create tokens under the real backend package/source tree
            # (may already exist from prior local runs — only assert we didn't require it)
            if not before:
                self.assertFalse(backend_tokens.exists())


if __name__ == "__main__":
    unittest.main()
