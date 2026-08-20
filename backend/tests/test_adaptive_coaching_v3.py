import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, HRV, RestingHeartRate
from app.database.models.activity import Activity, ActivityType
from app.database.models.lactate_threshold_history import LactateThresholdHistory
from app.services.athlete_calibration_service import AthleteCalibrationService
from app.services.athlete_state_service import AthleteStateService
from app.services.calibration_report_service import CalibrationReportService
from app.services.coaching_evaluation_service import CoachingEvaluationService
from app.services.coaching_model_health_service import CoachingModelHealthService
from app.services.comparable_session_service import ComparableSessionService
from app.services.context_adjusted_trend_service import ContextAdjustedTrendService
from app.services.load_variability_service import LoadVariabilityService
from app.services.next_best_workout_service import NextBestWorkoutService
from app.services.ppap_metrics_service import PpapMetricsService
from app.services.recommendation_outcome_service import RecommendationOutcomeService
from app.services.session_quality_service import SessionQualityService


class AdaptiveCoachingV3Tests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        engine = create_engine(f"sqlite:///{Path(self.tmpdir.name) / 'test.db'}")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
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
        self.running_type_id = running_type.id
        self.running_type = running_type
        self.ppap = PpapMetricsService(self.db, None)

    def tearDown(self):
        self.db.close()
        self.tmpdir.cleanup()

    def _run(
        self,
        activity_id: str,
        day: date,
        *,
        hr: int = 130,
        duration_s: int = 3600,
        name: str = "Easy",
        te: float = 2.5,
        temp: float | None = None,
        ascent: float | None = None,
        hr_drift: float | None = 3.0,
        decoupling: float | None = 2.0,
        ef: float | None = 0.025,
    ) -> Activity:
        activity = Activity(
            activity_id=activity_id,
            activity_name=name,
            start_time=datetime(day.year, day.month, day.day, 8, tzinfo=timezone.utc),
            duration=duration_s,
            distance=duration_s * 3.0,
            average_heart_rate=hr,
            average_speed=3.0,
            total_training_effect=te,
            temperature=temp,
            total_ascent=ascent,
            hr_drift_pct=hr_drift,
            decoupling_percent=decoupling,
            avg_efficiency_factor=ef,
            training_stress_score=50,
            activity_type_id=self.running_type_id,
        )
        activity.activity_type = self.running_type
        self.db.add(activity)
        self.db.commit()
        return activity

    def test_session_quality_easy_run(self):
        activity = self._run("q1", date(2026, 5, 20), hr=125, te=2.0)
        result = SessionQualityService(self.db, None).evaluate(activity)
        self.assertIsNotNone(result["quality_score"])
        self.assertGreaterEqual(result["quality_score"], 50)
        self.assertIn(result["session_type"], {"recovery_run", "easy_aerobic", "steady", "mixed", "unknown"})
        self.assertIn("comparability_note", result)

    def test_session_quality_missing_data_low_confidence(self):
        activity = Activity(
            activity_id="q2",
            activity_name="Sparse",
            start_time=datetime(2026, 5, 20, tzinfo=timezone.utc),
            duration=2400,
            activity_type_id=self.running_type_id,
        )
        activity.activity_type = self.running_type
        self.db.add(activity)
        self.db.commit()
        result = SessionQualityService(self.db, None).evaluate(activity)
        self.assertLessEqual(result["confidence"], 0.6)

    def test_comparable_sessions_same_distance(self):
        a1 = self._run("c1", date(2026, 5, 10), hr=130, duration_s=3600, temp=12)
        self._run("c2", date(2026, 5, 17), hr=132, duration_s=3500, temp=14)
        self._run("c3", date(2026, 5, 24), hr=128, duration_s=3700, temp=11)
        result = ComparableSessionService(self.db, None).find_comparable_sessions("c1", limit=5)
        self.assertEqual(result["status"], "ok")
        self.assertGreaterEqual(result["count"], 1)

    def test_comparable_missing_weather_still_works(self):
        self._run("w1", date(2026, 5, 10), temp=None)
        self._run("w2", date(2026, 5, 17), temp=None)
        result = ComparableSessionService(self.db, None).compare_to_personal_baseline("w1")
        self.assertEqual(result["status"], "ok")

    def test_context_adjusted_trend_heat_adjustment(self):
        for idx in range(6):
            self._run(
                f"h{idx}",
                date(2026, 5, 1) + timedelta(days=idx * 7),
                hr=130,
                temp=28.0 if idx >= 3 else 12.0,
                ef=0.022 if idx >= 3 else 0.026,
            )
        result = ContextAdjustedTrendService(self.db, None).analyze_metric(
            "easy_run_efficiency",
            end_date=date(2026, 6, 15),
            window_days=90,
        )
        self.assertIn("raw_trend", result)
        self.assertIn("context_adjusted_trend", result)
        self.assertTrue(
            any("heat" in a for a in result.get("adjustments", []))
            or result["context_adjusted_trend"].get("direction") is not None
        )

    def test_hilly_route_context(self):
        self._run("hill1", date(2026, 5, 10), ascent=400, ef=0.02, hr_drift=8)
        self._run("hill2", date(2026, 5, 17), ascent=50, ef=0.025, hr_drift=3)
        result = ContextAdjustedTrendService(self.db, None).analyze_metric(
            "hr_drift",
            end_date=date(2026, 5, 28),
            window_days=28,
        )
        self.assertIn("adjustments", result)

    def test_load_variability_flags(self):
        for idx in range(7):
            self._run(
                f"l{idx}",
                date(2026, 5, 20) + timedelta(days=idx),
                hr=160 if idx % 2 == 0 else 125,
                te=4.0 if idx % 2 == 0 else 2.0,
                name="Threshold" if idx % 2 == 0 else "Easy",
            )
        result = LoadVariabilityService(self.db, None).analyze(date(2026, 5, 26))
        self.assertIn("training_monotony", result)
        self.assertIn("flags", result)
        self.assertIn("confidence", result)

    def test_athlete_calibration_fallback_low_data(self):
        result = AthleteCalibrationService(self.db, None).calibrate_all(
            end_date=date(2026, 5, 28),
            lookback_days=60,
        )
        self.assertGreaterEqual(len(result["parameters"]), 4)
        for param in result["parameters"]:
            if param["sample_count"] < 12:
                self.assertFalse(param["use_personalized"])

    def test_athlete_calibration_strong_evidence_personalizes(self):
        service = AthleteCalibrationService(self.db, None)
        # Stable sample around -10% HRV drop (n>=12, low CV)
        samples = [-10.0 + (i % 3) * 0.2 for i in range(14)]
        result = service._parameter_result(
            "hrv_drop_warning_pct",
            -12.0,
            -10.0,
            len(samples),
            "median_hrv_delta_before_poor_session",
            samples,
        )
        self.assertTrue(result["use_personalized"])
        self.assertEqual(result["personalized_value"], -10.0)
        self.assertGreaterEqual(result["confidence"], 0.55)

    def test_recommendation_outcome_structure(self):
        self._run("o1", date(2026, 5, 21), hr=125)
        with patch.object(self.ppap, "get_readiness_component", return_value=70.0):
            with patch.object(self.ppap, "get_tsb", return_value=0.0):
                with patch.object(self.ppap, "get_ctl", return_value=50.0):
                    with patch.object(self.ppap, "get_atl", return_value=40.0):
                        service = RecommendationOutcomeService(self.db, None)
                        # Inject patched ppap into nested next service
                        service._ppap = self.ppap
                        service._next = NextBestWorkoutService(self.db, None, self.ppap)
                        result = service.evaluate_as_of(date(2026, 5, 20))
        self.assertIn("adherence", result)
        self.assertIn("outcome", result)
        self.assertIn("counterfactual_uncertainty", result)
        self.assertIn("short_term_response", result)

    def test_recommendation_outcome_favorable_vs_unfavorable(self):
        favorable = RecommendationOutcomeService._outcome_label(
            True,
            {"hrv_delta": 2.0, "session_quality": 80},
            {"fitness_change": 1.5},
        )
        unfavorable = RecommendationOutcomeService._outcome_label(
            False,
            {"hrv_delta": -8.0, "session_quality": 40},
            {"fitness_change": -3.0},
        )
        self.assertEqual(favorable, "favorable_response")
        self.assertEqual(unfavorable, "unfavorable_response")
        # Adherence is orthogonal — missing adherence does not flip outcome label alone
        inconclusive = RecommendationOutcomeService._outcome_label(
            None,
            {"hrv_delta": None, "session_quality": None},
            {"fitness_change": None},
        )
        self.assertEqual(inconclusive, "inconclusive")

    def test_session_classification_uncertainty_propagates_to_quality(self):
        from app.services.session_classifier_service import SessionClassifierService

        activity = self._run("unc1", date(2026, 5, 20), hr=145, te=3.2, name="Mixed")
        with patch.object(
            SessionClassifierService,
            "classify_activity",
            return_value={
                "session_type": "mixed",
                "confidence": 0.35,
                "evidence": ["ambiguous_hr_zones"],
            },
        ):
            result = SessionQualityService(self.db, None).evaluate(activity)
        self.assertLessEqual(result["confidence"], 0.6)
        self.assertTrue(
            any("classif" in f.lower() or "uncertain" in f.lower() for f in result.get("flags", []))
            or result["confidence"] < 0.55
        )

    def test_decision_trace_present(self):
        with patch.object(self.ppap, "get_readiness_component", return_value=30.0):
            with patch.object(self.ppap, "get_tsb", return_value=-5.0):
                with patch.object(self.ppap, "get_ctl", return_value=50.0):
                    with patch.object(self.ppap, "get_atl", return_value=45.0):
                        result = NextBestWorkoutService(self.db, None, self.ppap).recommend(
                            date(2026, 5, 28)
                        )
        self.assertEqual(result["workout_type"], "rest")
        self.assertTrue(result.get("decision_trace"))
        self.assertTrue(any(t["factor"] == "readiness" for t in result["decision_trace"]))

    def test_athlete_state_dimensions(self):
        state = AthleteStateService(self.db, None, self.ppap).build_state(date(2026, 5, 28))
        for key in (
            "fitness",
            "fatigue",
            "recovery",
            "durability",
            "aerobic_efficiency",
            "consistency",
        ):
            self.assertIn(key, state)
            self.assertIn("confidence", state[key])
            self.assertIn("evidence", state[key])

    def test_model_health_insufficient_or_healthy(self):
        health = CoachingModelHealthService(self.db, None).assess(date(2026, 5, 28))
        self.assertIn(health["status"], {"healthy", "degraded", "insufficient_data"})

    def test_calibration_report_bins(self):
        report = CalibrationReportService(self.db, None).build_report(
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 15),
            step_days=7,
        )
        self.assertIn("bins", report)
        self.assertIn("is_calibrated", report)
        self.assertIn("label_recommendation", report)

    def test_evaluation_payload(self):
        payload = CoachingEvaluationService(self.db, None).build_payload(
            end_date=date(2026, 5, 28),
            lookback_days=28,
        )
        self.assertIn("recommendation_accuracy", payload)
        self.assertIn("confidence_calibration", payload)
        self.assertIn("model_health", payload)
        self.assertIn("pb_calibration", payload)

    def test_no_lookahead_recommendation_outcome(self):
        """Recommendation uses only as-of data; future activities appear only in outcomes."""
        future = self._run("future", date(2026, 6, 1), hr=165, te=4.5, name="Threshold")
        service = RecommendationOutcomeService(self.db, None)
        with patch.object(service._next, "recommend", return_value={"workout_type": "easy_run", "confidence": 0.7}):
            result = service.evaluate_as_of(date(2026, 5, 20))
        self.assertEqual(result["recommended"], "easy_run")
        # future activity on June 1 is outside 3-day window from May 20
        self.assertIsNone(result["actual"])


if __name__ == "__main__":
    unittest.main()
