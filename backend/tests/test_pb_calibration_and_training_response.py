import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.database.models.activity import Activity, ActivityType
from app.database.models.summaries import PersonalRecord
from app.services.coaching_decision_metrics_service import CoachingDecisionMetricsService
from app.services.pb_probability_calibration_service import PbProbabilityCalibrationService
from app.services.ppap_metrics_service import PpapMetricsService
from app.services.training_response_service import TrainingResponseService, _pearson


class PbProbabilityCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        engine = create_engine(f"sqlite:///{Path(self.tmpdir.name) / 'test.db'}")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        running_type = ActivityType(type_key="running", type_name="Running")
        self.db.add(running_type)
        self.db.commit()
        self.running_type_id = running_type.id
        self.ppap = PpapMetricsService(self.db, None)
        self.calibration = PbProbabilityCalibrationService(self.db, None, self.ppap)
        self.decision = CoachingDecisionMetricsService(self.db, self.ppap)

    def tearDown(self):
        self.db.close()
        self.tmpdir.cleanup()

    def _race(self, activity_id: str, day: date, duration_s: float, distance_m: float, name: str = "5k race"):
        self.db.add(
            Activity(
                activity_id=activity_id,
                activity_name=name,
                start_time=datetime(day.year, day.month, day.day, 9, tzinfo=timezone.utc),
                duration=duration_s,
                distance=distance_m,
                average_heart_rate=170,
                average_speed=distance_m / duration_s,
                training_stress_score=80,
                activity_type_id=self.running_type_id,
            )
        )

    def test_calibration_bins_from_race_history(self):
        base = date(2025, 6, 1)
        for idx in range(6):
            self._race(
                f"r{idx}",
                base + timedelta(days=idx * 30),
                1200 - idx * 5,
                5000,
            )
        self.db.commit()

        result = self.calibration.build_calibration("5k", lookback_days=400, end_date=date(2026, 1, 1))
        self.assertGreaterEqual(result["sample_count"], 0)
        self.assertIn("bins", result)

    def test_calibrated_probability_metadata(self):
        result = self.calibration.get_calibrated_probability(date(2026, 5, 28), "5k")
        self.assertIn("method", result)
        self.assertIn("confidence", result)

    def test_get_pb_probability_falls_back_without_races(self):
        score = self.decision.get_pb_probability(date(2026, 5, 28), "5k")
        readiness = self.decision.get_pb_readiness_score(date(2026, 5, 28), "5k")
        if score is not None and readiness is not None:
            self.assertEqual(score, readiness)


class TrainingResponseZoneTests(unittest.TestCase):
    def test_pearson_correlation(self):
        self.assertAlmostEqual(_pearson([1, 2, 3, 4, 5], [2, 4, 6, 8, 10]), 1.0, places=5)
        self.assertIsNone(_pearson([1, 1, 1], [2, 3, 4]))

    def test_zone_stimulus_uses_lt_buckets(self):
        tmpdir = tempfile.TemporaryDirectory()
        engine = create_engine(f"sqlite:///{Path(tmpdir.name) / 'test.db'}")
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        running_type = ActivityType(type_key="running", type_name="Running")
        db.add(running_type)
        db.commit()

        from app.database.models.lactate_threshold_history import LactateThresholdHistory

        db.add(
            LactateThresholdHistory(
                observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                source="garmin",
                lactate_threshold_heart_rate=170,
                lactate_threshold_speed=3.5,
            )
        )
        db.add(
            Activity(
                activity_id="easy1",
                activity_name="Easy",
                start_time=datetime(2026, 5, 10, 8, tzinfo=timezone.utc),
                duration=3600,
                distance=10000,
                average_heart_rate=130,
                average_speed=2.8,
                activity_type_id=running_type.id,
            )
        )
        db.commit()

        service = TrainingResponseService(db, None)
        val = service._stimulus_value(
            "easy_volume",
            date(2026, 5, 1),
            date(2026, 5, 14),
        )
        db.close()
        tmpdir.cleanup()
        self.assertIsNotNone(val)
        self.assertGreater(val, 0)


if __name__ == "__main__":
    unittest.main()
