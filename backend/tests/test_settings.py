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
        self.assertTrue(s.REDIS_ENABLED)
        self.assertEqual(s.REDIS_PORT, 6379)
        self.assertFalse(s.GARMIN_IS_CN)
        self.assertEqual(s.LOG_LEVEL, "INFO")
        self.assertIsNone(s.REDIS_PASSWORD)
        self.assertIsNone(s.GARMIN_TOKEN_FILE)

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
            s = Settings(
                _env_file=None,
                DATA_DIR=str(data),
                TOKEN_DIR=str(tokens),
            )
            self.assertTrue(Path(s.DATA_DIR).is_dir())
            self.assertTrue(Path(s.TOKEN_DIR).is_dir())


if __name__ == "__main__":
    unittest.main()
