"""Tester for konsolidert pydantic Settings."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import Settings, get_settings


class SettingsConsolidationTests(unittest.TestCase):
    def test_defaults_without_env(self):
        with patch.dict(os.environ, {}, clear=True):
            # Unngå at prosjektets .env påvirker — bruk env_file som ikke finnes
            s = Settings(_env_file=None)
        self.assertFalse(s.REDIS_ENABLED)
        self.assertEqual(s.REDIS_PORT, 6379)
        self.assertFalse(s.GARMIN_IS_CN)
        self.assertEqual(s.LOG_LEVEL, "INFO")
        self.assertIsNone(s.REDIS_PASSWORD)
        self.assertIsNone(s.GARMIN_TOKEN_FILE)
        self.assertFalse(s.DEBUG)
        self.assertEqual(s.ENVIRONMENT, "local")
        self.assertEqual(s.allowed_host_list(), [])

    def test_bool_and_int_from_env_strings(self):
        env = {
            "REDIS_ENABLED": "false",
            "REDIS_PORT": "6380",
            "GARMIN_IS_CN": "true",
            "TELEGRAM_REAUTH_COOLDOWN_SECONDS": "60",
        }
        with patch.dict(os.environ, env, clear=False):
            s = Settings(_env_file=None)
        self.assertFalse(s.REDIS_ENABLED)
        self.assertEqual(s.REDIS_PORT, 6380)
        self.assertTrue(s.GARMIN_IS_CN)
        self.assertEqual(s.TELEGRAM_REAUTH_COOLDOWN_SECONDS, 60)

    def test_empty_optional_strings_become_none(self):
        env = {"REDIS_PASSWORD": "", "GARMIN_TOKEN_FILE": ""}
        with patch.dict(os.environ, env, clear=False):
            s = Settings(_env_file=None)
        self.assertIsNone(s.REDIS_PASSWORD)
        self.assertIsNone(s.GARMIN_TOKEN_FILE)

    def test_get_settings_is_cached(self):
        get_settings.cache_clear()
        a = get_settings()
        b = get_settings()
        self.assertIs(a, b)
        get_settings.cache_clear()

    def test_creates_data_and_token_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            tokens = Path(tmp) / "tokens"
            env_clear = {
                "TRAININGSANALYSE_DATA_DIR": "",
                "DESKTOP_MODE": "false",
            }
            with patch.dict(os.environ, env_clear, clear=False):
                s = Settings(
                    _env_file=None,
                    DATA_DIR=str(data),
                    TOKEN_DIR=str(tokens),
                    DESKTOP_MODE=False,
                    TRAININGSANALYSE_DATA_DIR=None,
                )
            self.assertTrue(Path(s.DATA_DIR).is_dir())
            self.assertTrue(Path(s.TOKEN_DIR).is_dir())

    def test_trainingsanalyse_data_dir_derives_subdirs_and_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Pass non-canonical temp path (Windows CI may use 8.3 short names).
            root = Path(tmp) / "appdata"
            with patch.dict(os.environ, {"DESKTOP_MODE": "false"}, clear=False):
                s = Settings(
                    _env_file=None,
                    TRAININGSANALYSE_DATA_DIR=str(root),
                    DESKTOP_MODE=False,
                )
            expected_root = root.expanduser().resolve()
            self.assertEqual(Path(s.DATA_DIR).resolve(), (expected_root / "data").resolve())
            self.assertEqual(Path(s.TOKEN_DIR).resolve(), (expected_root / "tokens").resolve())
            self.assertEqual(Path(s.LOG_DIR).resolve(), (expected_root / "logs").resolve())
            self.assertEqual(Path(s.BACKUP_DIR).resolve(), (expected_root / "backups").resolve())
            self.assertEqual(Path(s.FIT_DATA_DIR).resolve(), (expected_root / "fit").resolve())
            self.assertEqual(Path(s.CACHE_DIR).resolve(), (expected_root / "cache").resolve())
            self.assertEqual(Path(s.EXPORT_DIR).resolve(), (expected_root / "exports").resolve())
            self.assertTrue(s.DATABASE_URL.startswith("sqlite:///"))
            self.assertIn("treningsanalyse.db", s.DATABASE_URL)
            self.assertTrue(Path(s.DATA_DIR).is_dir())
            self.assertTrue(Path(s.TOKEN_DIR).is_dir())

    def test_explicit_database_url_wins_over_data_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "appdata"
            custom = Path(tmp) / "custom.db"
            url = f"sqlite:///{custom.resolve().as_posix()}"
            s = Settings(
                _env_file=None,
                TRAININGSANALYSE_DATA_DIR=str(root),
                DATABASE_URL=url,
            )
            self.assertEqual(s.DATABASE_URL, url)


if __name__ == "__main__":
    unittest.main()
