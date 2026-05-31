import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.database.models.activity import Activity, ActivityType
from app.services.sync_modules.metrics_service import SyncMetricsService, tss_needs_refresh


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


if __name__ == "__main__":
    unittest.main()
