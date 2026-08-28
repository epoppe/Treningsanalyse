"""Tester for desktop config/.env og Garmin sync readiness."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from app.config import Settings, load_env_files, reset_settings_cache, user_config_env_path
from app.services.sync_garmin_readiness import (
    assert_garmin_sync_ready,
    build_garmin_sync_status,
    garmin_credentials_configured,
    has_garmin_token_cache,
)


def _isolated_settings(tmp: Path, **overrides) -> Settings:
    defaults = {
        "_env_file": None,
        "GARMIN_EMAIL": "",
        "GARMIN_PASSWORD": "",
        "TRAININGSANALYSE_DATA_DIR": str(tmp),
        "DESKTOP_MODE": True,
        "TOKEN_DIR": str(tmp / "tokens"),
        "DATA_DIR": str(tmp / "data"),
    }
    defaults.update(overrides)
    return Settings(**defaults)


class DesktopConfigEnvTests(unittest.TestCase):
    def test_user_config_env_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            expected = Path(tmp) / "config" / ".env"
            self.assertEqual(user_config_env_path(tmp), expected)

    def test_load_env_files_reads_appdata_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "config"
            config_dir.mkdir(parents=True)
            env_file = config_dir / ".env"
            env_file.write_text("GARMIN_EMAIL=desktop@test.example\nGARMIN_PASSWORD=secret\n")

            missing_backend_env = Path(tmp) / "missing-backend.env"
            with patch.dict(
                os.environ,
                {"TRAININGSANALYSE_DATA_DIR": tmp},
                clear=False,
            ), patch("app.config.ENV_FILE", missing_backend_env):
                os.environ.pop("GARMIN_EMAIL", None)
                os.environ.pop("GARMIN_PASSWORD", None)
                load_env_files(data_root=tmp)
                self.assertEqual(os.environ.get("GARMIN_EMAIL"), "desktop@test.example")


class GarminSyncReadinessTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_config_not_ready(self):
        settings = _isolated_settings(self.root)
        with patch("app.services.sync_garmin_readiness.settings", settings):
            status = build_garmin_sync_status()
            self.assertFalse(status["ready"])
            self.assertIn("Garmin Connect", status["detail"] or "")

    def test_credentials_ready(self):
        settings = _isolated_settings(
            self.root,
            GARMIN_EMAIL="runner@example.com",
            GARMIN_PASSWORD="pw",
        )
        with patch("app.services.sync_garmin_readiness.settings", settings):
            self.assertTrue(garmin_credentials_configured())
            status = build_garmin_sync_status()
            self.assertTrue(status["ready"])

    def test_assert_raises_422_when_not_ready(self):
        settings = _isolated_settings(self.root)
        with patch("app.services.sync_garmin_readiness.settings", settings):
            with self.assertRaises(HTTPException) as ctx:
                assert_garmin_sync_ready()
            self.assertEqual(ctx.exception.status_code, 422)

    def test_token_cache_ready_without_password(self):
        settings = _isolated_settings(self.root)
        token_path = Path(settings.TOKEN_DIR)
        token_path.mkdir(parents=True, exist_ok=True)
        (token_path / "garmin_tokens.json").write_text('{"di_token":"x","di_refresh_token":"y"}')
        with patch("app.services.sync_garmin_readiness.settings", settings):
            self.assertTrue(has_garmin_token_cache())
            status = build_garmin_sync_status()
            self.assertTrue(status["ready"])


if __name__ == "__main__":
    unittest.main()
