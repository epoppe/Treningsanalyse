import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.database.models.activity import Activity, ActivityType
from app.database.models.lactate_threshold_history import LactateThresholdHistory
from app.services.adaptive_threshold_service import AdaptiveThresholdService
from app.services.coaching_backtest_service import CoachingBacktestService
from app.services.next_best_workout_service import NextBestWorkoutService
from app.services.ppap_metrics_service import PpapMetricsService


class AdaptiveThresholdServiceTests(unittest.TestCase):
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
        self.db.add(
            LactateThresholdHistory(
                observed_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
                source="garmin",
                lactate_threshold_heart_rate=170,
                lactate_threshold_speed=3.5,
            )
        )
        self.db.commit()
        self.service = AdaptiveThresholdService(self.db, None)

    def tearDown(self):
        self.db.close()
        self.tmpdir.cleanup()

    def test_fallback_lt2_multiplier_when_no_stable_runs(self):
        result = self.service.estimate_lt1(end_date=date(2026, 5, 28))
        self.assertTrue(result["fallback_used"])
        self.assertAlmostEqual(result["lt1_hr"], 170 * 0.85, delta=1)
        self.assertIn("not a direct lactate measurement", result["limitations"][0].lower())

    def test_stable_easy_runs_improve_confidence(self):
        for idx in range(4):
            self.db.add(
                Activity(
                    activity_id=f"s{idx}",
                    activity_name="Easy",
                    start_time=datetime(2026, 5, 10 + idx, 8, tzinfo=timezone.utc),
                    duration=45 * 60,
                    average_heart_rate=130,
                    average_speed=2.8,
                    hr_drift_pct=2.0,
                    activity_type_id=self.running_type_id,
                )
            )
        self.db.commit()
        result = self.service.estimate_lt1(end_date=date(2026, 5, 28))
        self.assertGreater(result["confidence"], 0.35)
        self.assertFalse(result["fallback_used"])


class NextBestWorkoutServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        engine = create_engine(f"sqlite:///{Path(self.tmpdir.name) / 'test.db'}")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.ppap = PpapMetricsService(self.db, None)
        self.service = NextBestWorkoutService(self.db, None, self.ppap)

    def tearDown(self):
        self.db.close()
        self.tmpdir.cleanup()

    def test_recommends_rest_when_readiness_very_low(self):
        with patch.object(self.ppap, "get_readiness_component", return_value=30.0):
            with patch.object(self.ppap, "get_tsb", return_value=-5.0):
                result = self.service.recommend(date(2026, 5, 28))
        self.assertEqual(result["workout_type"], "rest")
        self.assertIn("rationale", result)
        self.assertIn("alternative", result)

    def test_guardrail_blocks_back_to_back_hard(self):
        running_type = ActivityType(type_key="running", type_name="Running")
        self.db.add(running_type)
        self.db.add(
            LactateThresholdHistory(
                observed_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
                source="garmin",
                lactate_threshold_heart_rate=170,
                lactate_threshold_speed=3.5,
            )
        )
        self.db.commit()
        self.db.add(
            Activity(
                activity_id="hard1",
                activity_name="Threshold intervals",
                start_time=datetime(2026, 5, 27, 18, tzinfo=timezone.utc),
                duration=3600,
                average_heart_rate=165,
                average_speed=3.5,
                total_training_effect=4.5,
                activity_type_id=running_type.id,
            )
        )
        self.db.commit()
        with patch.object(self.ppap, "get_readiness_component", return_value=80.0):
            with patch.object(self.ppap, "get_tsb", return_value=5.0):
                with patch.object(self.ppap, "get_ctl", return_value=60.0):
                    with patch.object(self.ppap, "get_atl", return_value=55.0):
                        with patch.object(self.ppap, "get_hrv_delta_pct", return_value=0.0):
                            with patch.object(self.ppap, "get_sleep_debt_hours", return_value=0.0):
                                result = self.service.recommend(date(2026, 5, 28))
        self.assertIn(result["workout_type"], {"easy_run", "recovery_run"})


class CoachingBacktestServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        engine = create_engine(f"sqlite:///{Path(self.tmpdir.name) / 'test.db'}")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.service = CoachingBacktestService(self.db, None)

    def tearDown(self):
        self.db.close()
        self.tmpdir.cleanup()

    def test_evaluate_period_structure(self):
        result = self.service.evaluate_period(
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 15),
            step_days=7,
        )
        self.assertIn("evaluations", result)
        self.assertIn("summary", result)
        self.assertGreaterEqual(len(result["evaluations"]), 2)

    def test_as_of_uses_no_future_lt_history(self):
        self.db.add(
            LactateThresholdHistory(
                observed_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
                source="garmin",
                lactate_threshold_heart_rate=165,
                lactate_threshold_speed=3.2,
            )
        )
        self.db.commit()
        evaluation = self.service._evaluate_as_of(date(2026, 4, 1))
        self.assertEqual(evaluation["as_of_date"], "2026-04-01")
        self.assertIn("recommended_workout", evaluation)


if __name__ == "__main__":
    unittest.main()
