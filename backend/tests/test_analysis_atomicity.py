"""Tester for atomisk lagring i AnalysisService og SyncMetricsService."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import tempfile
from pathlib import Path

from app.database.models import Base
from app.database.models.activity import Activity, ActivityType
from app.services.analysis_service import AnalysisService
from app.services.sync_modules.metrics_service import SyncMetricsService
from app.storage import DataStorage


class AnalysisAtomicityTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmpdir.name) / "test.db"
        self.engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.storage = DataStorage(str(Path(self.tmpdir.name) / "data"))
        self.service = AnalysisService(self.storage)

        running_type = ActivityType(type_key="running", type_name="Running")
        self.db.add(running_type)
        self.db.commit()

        start = datetime(2024, 6, 1, 8, 0, 0, tzinfo=timezone.utc)
        self.db.add(
            Activity(
                activity_id="9100",
                activity_name="Atomic test run",
                start_time=start,
                distance=10000,
                duration=3600,
                average_speed=2.78,
                average_heart_rate=150,
                activity_type_id=running_type.id,
            )
        )
        self.db.commit()

        records = []
        for second in range(0, 3601, 5):
            records.append(
                {
                    "activity_id": 9100,
                    "timestamp": start + timedelta(seconds=second),
                    "distance": 2.78 * second,
                    "speed": 2.78,
                    "heart_rate": 150,
                }
            )
        self.storage.save_activity_details(records)

    def tearDown(self):
        self.db.close()
        self.tmpdir.cleanup()

    def test_negative_split_persist_false_defers_commit(self):
        with patch.object(self.db, "commit", wraps=self.db.commit) as commit_mock:
            result = self.service.calculate_negative_split(9100, self.db, persist=False)
        self.assertIsNotNone(result)
        self.assertIn("negative_split_percent", result)
        commit_mock.assert_not_called()

        self.db.rollback()
        activity = self.db.query(Activity).filter_by(activity_id="9100").first()
        self.assertIsNone(activity.negative_split_percent)

        self.service.calculate_negative_split(9100, self.db, persist=True)
        activity = self.db.query(Activity).filter_by(activity_id="9100").first()
        self.assertIsNotNone(activity.negative_split_percent)

    def test_sync_metrics_single_commit_on_success(self):
        sync_service = MagicMock()
        sync_service.db = self.db
        sync_service.storage = self.storage
        sync_service.analysis_service = self.service

        metrics = SyncMetricsService(sync_service)
        with patch.object(self.db, "commit", wraps=self.db.commit) as commit_mock:
            result = metrics.calculate_metrics_for_new_activity("9100")

        self.assertFalse(result["errors"])
        self.assertTrue(
            result["negative_split_calculated"]
            or result["decoupling_calculated"]
            or result["tss_calculated"]
        )
        commit_mock.assert_called_once()

    def test_sync_metrics_rollback_on_commit_failure(self):
        sync_service = MagicMock()
        sync_service.db = self.db
        sync_service.storage = self.storage
        sync_service.analysis_service = self.service

        metrics = SyncMetricsService(sync_service)
        with patch.object(self.db, "commit", side_effect=RuntimeError("disk full")):
            with patch.object(self.db, "rollback") as rollback_mock:
                result = metrics.calculate_metrics_for_new_activity("9100")

        rollback_mock.assert_called()
        self.assertTrue(result["errors"])


if __name__ == "__main__":
    unittest.main()
