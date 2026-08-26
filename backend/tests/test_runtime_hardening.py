"""Runtime hardening: readiness HTTP status and debug gating."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient


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
        import tempfile
        from pathlib import Path

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        from app import config as config_mod
        from app.database.migrations import run_migrations
        from app.database.session import get_db

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "debug.db"
            url = f"sqlite:///{db_path.resolve().as_posix()}"
            engine = create_engine(
                url,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
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
                with patch.object(config_mod.settings, "DEBUG", True):
                    res = self.client.get("/api/debug/db-info")
                self.assertEqual(res.status_code, 200)
                self.assertIn("activity_count", res.json())
            finally:
                self.app.dependency_overrides.clear()
                engine.dispose()


if __name__ == "__main__":
    unittest.main()
