import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.database.models.activity import Activity, ActivityType
from app.services.coaching_decision_metrics_service import CoachingDecisionMetricsService
from app.services.ppap_metrics_service import PpapMetricsService


class CoachingDecisionMetricsTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        engine = create_engine(f"sqlite:///{Path(self.tmpdir.name) / 'test.db'}")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        running_type = ActivityType(type_key="running", type_name="Running")
        self.db.add(running_type)
        self.db.commit()
        self.running_type_id = running_type.id
        self.running_type = running_type
        self.ppap = PpapMetricsService(self.db, None)
        self.service = CoachingDecisionMetricsService(self.db, self.ppap)

    def tearDown(self):
        self.db.close()
        self.tmpdir.cleanup()

    def test_consistency_score_counts_training_days(self):
        base = datetime(2026, 5, 1, 8, tzinfo=timezone.utc)
        for offset in (0, 2, 4, 6):
            self.db.add(
                Activity(
                    activity_id=f"c-{offset}",
                    activity_name="Run",
                    start_time=base + timedelta(days=offset),
                    duration=3600,
                    distance=10000,
                    activity_type_id=self.running_type_id,
                )
            )
        self.db.commit()
        score = self.service.get_consistency_score(date(2026, 5, 28), window_days=28)
        self.assertIsNotNone(score)
        self.assertGreater(score, 0)

    def test_long_run_quality_penalizes_drift(self):
        activity = Activity(
            activity_id="lr1",
            activity_name="Long",
            start_time=datetime(2026, 5, 20, 8, tzinfo=timezone.utc),
            duration=90 * 60,
            distance=18000,
            pace_drop_pct=8.0,
            hr_drift_pct=6.0,
            activity_type_id=self.running_type_id,
        )
        activity.activity_type = self.running_type
        good = self.service.compute_long_run_quality(activity)
        activity.fatigue_resistance_score = 85.0
        better = self.service.compute_long_run_quality(activity)
        self.assertIsNotNone(good)
        self.assertIsNotNone(better)
        self.assertGreater(better, good)

    def test_polarization_score_peaks_near_80_20(self):
        with patch.object(self.ppap, "get_coaching_zone_pct", side_effect=lambda _d, k: {
            "coaching.zone1_pct": 80.0,
            "coaching.zone2_pct": 5.0,
            "coaching.zone3_pct": 15.0,
        }.get(k)):
            score = self.service.get_polarization_score(date.today())
        self.assertGreater(score, 85.0)

    def test_recommended_workout_rest_when_readiness_very_low(self):
        with patch.object(self.ppap, "get_readiness_component", return_value=30.0):
            with patch.object(self.ppap, "get_tsb", return_value=-5.0):
                with patch.object(self.ppap, "get_ctl", return_value=50.0):
                    with patch.object(self.ppap, "get_atl", return_value=45.0):
                        workout = self.service.get_recommended_workout(date.today())
        self.assertEqual(workout, "rest")

    def test_build_coaching_snapshot_has_required_keys(self):
        with patch.object(self.service, "get_consistency_score", return_value=78.0):
            snapshot = self.service.build_coaching_snapshot(date(2026, 5, 28))
        self.assertIn("readiness_by_event", snapshot)
        self.assertIn("recommended_workout", snapshot)
        self.assertIn("limiting_factors", snapshot)
        self.assertIn("data_gaps", snapshot)


if __name__ == "__main__":
    unittest.main()
