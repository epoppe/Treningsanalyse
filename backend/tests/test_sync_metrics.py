import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.database.models.activity import Activity, ActivityType
from app.services.analysis_service import AnalysisService
from app.services.sync_modules.metrics_service import SyncMetricsService, tss_needs_refresh
from app.storage import DataStorage


class TssNeedsRefreshTests(unittest.TestCase):
    def test_missing_tss(self):
        activity = Activity(activity_id="1", training_stress_score=None, epoc=None)
        self.assertTrue(tss_needs_refresh(activity))

    def test_epoc_mismatch(self):
        activity = Activity(activity_id="1", training_stress_score=50.0, epoc=180.0)
        self.assertTrue(tss_needs_refresh(activity))

    def test_epoc_matches(self):
        activity = Activity(activity_id="1", training_stress_score=180.0, epoc=180.0)
        self.assertFalse(tss_needs_refresh(activity))


class RefreshMetricsAfterTeSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        engine = create_engine(f"sqlite:///{Path(self.tmpdir.name) / 'test.db'}")
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)
        self.db = self.Session()
        self.sync_service = MagicMock()
        self.sync_service.db = self.db
        self.sync_service.storage = MagicMock()
        self.metrics = SyncMetricsService(self.sync_service)

        run_type = ActivityType(type_key="running", type_name="Running")
        self.db.add(run_type)
        self.db.flush()
        self.activity = Activity(
            activity_id="100",
            activity_name="Test",
            start_time=datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc),
            duration=3600,
            training_stress_score=42.0,
            epoc=180.0,
            activity_type_id=run_type.id,
        )
        self.db.add(self.activity)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.tmpdir.cleanup()

    @patch.object(SyncMetricsService, "_recalculate_performance_snapshots_once")
    def test_refresh_updates_tss_from_epoc(self, mock_snapshots):
        start = datetime(2026, 5, 27, tzinfo=timezone.utc)
        end = datetime(2026, 5, 28, tzinfo=timezone.utc)

        with patch("app.services.training_stress_service.TrainingStressService") as mock_tss_cls:
            mock_tss = mock_tss_cls.return_value
            mock_tss.calculate_tss_for_activity.return_value = 180.0

            result = self.metrics.refresh_metrics_after_te_sync(start, end)

        self.db.refresh(self.activity)
        self.assertEqual(result["tss_refreshed"], 1)
        self.assertEqual(self.activity.training_stress_score, 180.0)
        mock_snapshots.assert_called_once()


class SyncMetricsBatchTests(unittest.TestCase):
    def test_begin_end_batch_triggers_single_snapshot(self):
        sync_service = MagicMock()
        metrics = SyncMetricsService(sync_service)

        with patch.object(metrics, "_recalculate_performance_snapshots_once") as mock_once:
            metrics.begin_batch()
            metrics._snapshot_recalc_pending = True
            metrics.end_batch()
            mock_once.assert_called_once()

        with patch.object(metrics, "_recalculate_performance_snapshots_once") as mock_once:
            metrics.begin_batch()
            metrics.end_batch()
            mock_once.assert_not_called()


class TreadmillDerivedMetricsTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        engine = create_engine(f"sqlite:///{Path(self.tmpdir.name) / 'test.db'}")
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)
        self.db = self.Session()
        self.storage = DataStorage(str(Path(self.tmpdir.name) / "data"))

        treadmill_type = ActivityType(type_key="treadmill_running", type_name="Treadmill")
        self.db.add(treadmill_type)
        self.db.commit()
        self.treadmill_type_id = treadmill_type.id

        self.sync_service = MagicMock()
        self.sync_service.db = self.db
        self.sync_service.storage = self.storage
        self.sync_service.analysis_service = AnalysisService(self.storage)
        self.metrics = SyncMetricsService(self.sync_service)

    def tearDown(self):
        self.db.close()
        self.tmpdir.cleanup()

    def _seed_treadmill_activity(self, activity_id: str = "9001"):
        start = datetime(2024, 4, 26, 14, 17, 36, tzinfo=timezone.utc)
        self.db.add(
            Activity(
                activity_id=activity_id,
                activity_name="Treadmill",
                start_time=start,
                duration=2400,
                distance=8000,
                average_speed=2.2,
                average_heart_rate=152,
                activity_type_id=self.treadmill_type_id,
            )
        )
        self.db.commit()

        records = []
        for second in range(0, 2401, 4):
            records.append(
                {
                    "activity_id": int(activity_id),
                    "timestamp": start + timedelta(seconds=second),
                    "distance": 2.2 * second,
                    "speed": 2.2,
                    "heart_rate": 150 + (second // 600),
                    "cadence": 170,
                }
            )
        self.storage.save_activity_details(records)

    def test_treadmill_gets_all_three_derived_metrics(self):
        self._seed_treadmill_activity()
        self.metrics.begin_batch()
        result = self.metrics.calculate_metrics_for_new_activity("9001", skip_snapshot_recalc=True)
        self.metrics.end_batch()

        activity = self.db.query(Activity).filter_by(activity_id="9001").one()
        self.assertTrue(result["negative_split_calculated"])
        self.assertTrue(result["decoupling_calculated"])
        self.assertTrue(result["running_economy_calculated"])
        self.assertIsNotNone(activity.negative_split_percent)
        self.assertIsNotNone(activity.decoupling_percent)
        self.assertIsNotNone(activity.running_economy)


if __name__ == "__main__":
    unittest.main()
