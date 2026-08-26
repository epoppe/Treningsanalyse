"""Runtime hardening: readiness HTTP status and debug gating."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.database.migrations import run_migrations
from app.database.session import get_db
from tests.sqlite_test_utils import dispose_engine, file_sqlite_url, make_file_engine


class RuntimeHardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Import after env defaults; SKIP_GARMIN_INIT already used in CI smoke.
        import os

        os.environ.setdefault("SKIP_GARMIN_INIT", "true")
        from app.main import app

        cls.app = app
        cls.client = TestClient(app)

    def test_health_live_ok(self):
        res = self.client.get("/health/live")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json().get("status"), "ok")

    def test_health_ready_ok_or_503(self):
        res = self.client.get("/health/ready")
        self.assertIn(res.status_code, (200, 503))
        body = res.json()
        self.assertIn(body.get("status"), ("ok", "not_ready"))
        if res.status_code == 200:
            self.assertEqual(body["status"], "ok")
        else:
            self.assertEqual(body["status"], "not_ready")

    def test_debug_db_info_hidden_without_debug(self):
        from app import config as config_mod

        with patch.object(config_mod.settings, "DEBUG", False):
            res = self.client.get("/api/debug/db-info")
        self.assertEqual(res.status_code, 404)

    def test_debug_db_info_available_when_debug(self):
        """Isolated temp DB — does not depend on backend/data/treningsanalyse.db."""
        from app import config as config_mod
        import app.main as main_mod

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "debug.db"
            url = file_sqlite_url(db_path)
            engine = make_file_engine(url)
            try:
                run_migrations(engine, url)
                Session = sessionmaker(bind=engine)

                def override_get_db():
                    db = Session()
                    try:
                        yield db
                    finally:
                        db.close()

                self.app.dependency_overrides[get_db] = override_get_db
                try:
                    with patch.object(config_mod.settings, "DEBUG", True), patch.object(
                        main_mod, "db_engine", engine
                    ):
                        res = self.client.get("/api/debug/db-info")
                    self.assertEqual(res.status_code, 200)
                    body = res.json()
                    self.assertEqual(body.get("activity_count"), 0)
                    self.assertTrue(body.get("schema_at_head"))
                    self.assertIsNotNone(body.get("schema_version"))
                finally:
                    self.app.dependency_overrides.clear()
            finally:
                dispose_engine(engine)


if __name__ == "__main__":
    unittest.main()
