"""Recommendation history API — execution filters and richer columns."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models.base import Base
from app.database.models.coaching_v5 import RecommendationExecution, RecommendationRecord


def _rec(**overrides) -> RecommendationRecord:
    defaults = dict(
        as_of_date=date(2026, 8, 20),
        model_version="test",
        decision_engine_version="test",
        calibration_version="test",
        application_version="test",
        config_hash="abc",
        recommended_workout_type="easy_run",
        decision_status="recommend",
        is_shadow=False,
        is_active=True,
        generated_at=datetime(2026, 8, 20, 8, 0, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return RecommendationRecord(**defaults)


class RecommendationHistoryApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        engine = create_engine(f"sqlite:///{Path(self.tmpdir.name) / 'hist.db'}")
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)
        self.db = self.Session()

        followed = _rec(as_of_date=date(2026, 8, 22), recommended_workout_type="threshold")
        modified = _rec(as_of_date=date(2026, 8, 21), recommended_workout_type="easy_run")
        skipped = _rec(as_of_date=date(2026, 8, 20), recommended_workout_type="long_run")
        self.db.add_all([followed, modified, skipped])
        self.db.flush()

        self.db.add_all(
            [
                RecommendationExecution(
                    recommendation_id=followed.id,
                    activity_id=None,
                    execution_status="followed",
                    planned_type="threshold",
                    actual_type="threshold",
                    overall_adherence=0.92,
                    linked_at=datetime(2026, 8, 22, 18, 0, tzinfo=timezone.utc),
                ),
                RecommendationExecution(
                    recommendation_id=modified.id,
                    activity_id=None,
                    execution_status="modified",
                    planned_type="easy_run",
                    actual_type="recovery",
                    overall_adherence=0.55,
                    linked_at=datetime(2026, 8, 21, 18, 0, tzinfo=timezone.utc),
                ),
            ]
        )
        self.db.commit()

        from app.main import app
        from app.dependencies import get_db, get_data_storage

        def _db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_data_storage] = lambda: None
        self.app = app
        self.client = TestClient(app)

    def tearDown(self):
        from app.main import app

        app.dependency_overrides.clear()
        self.db.close()
        self.tmpdir.cleanup()

    def test_all_includes_execution_columns(self):
        res = self.client.get("/api/dashboard/recommendation-history", params={"limit": 10})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["filter"], "all")
        self.assertGreaterEqual(body["count"], 3)
        statuses = {item["execution_status"] for item in body["items"]}
        self.assertIn("followed", statuses)
        self.assertIn("modified", statuses)
        self.assertIn("skipped", statuses)
        followed = next(i for i in body["items"] if i["execution_status"] == "followed")
        self.assertEqual(followed["actual_type"], "threshold")
        self.assertAlmostEqual(followed["execution_quality"], 0.92)
        self.assertIn("disclaimer", body)

    def test_filter_followed(self):
        res = self.client.get(
            "/api/dashboard/recommendation-history",
            params={"limit": 10, "execution": "followed"},
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["filter"], "followed")
        self.assertTrue(body["items"])
        self.assertTrue(all(i["execution_status"] == "followed" for i in body["items"]))

    def test_filter_skipped_uses_fallback(self):
        res = self.client.get(
            "/api/dashboard/recommendation-history",
            params={"limit": 10, "execution": "skipped"},
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["filter"], "skipped")
        self.assertTrue(body["items"])
        self.assertTrue(all(i["execution_status"] == "skipped" for i in body["items"]))


if __name__ == "__main__":
    unittest.main()
