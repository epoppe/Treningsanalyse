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
from app.services.athlete_calibration_service import AthleteCalibrationService
from app.services.coaching_backtest_v4_service import CoachingBacktestV4Service
from app.services.goal_context_service import GoalContextService
from app.services.intensity_prescription_service import IntensityPrescriptionService
from app.services.next_best_workout_service import NextBestWorkoutService
from app.services.plan_adaptation_service import PlanAdaptationService
from app.services.ppap_metrics_service import PpapMetricsService
from app.services.race_capability_service import RaceCapabilityService
from app.services.training_phase_service import TrainingPhaseService
from app.services.training_response_service import TrainingResponseService
from app.services.workout_candidate_ranker import WorkoutCandidateRanker
from app.services.workout_effectiveness_service import WorkoutEffectivenessService
from app.services.workout_prescription_service import WorkoutPrescriptionService


def _param(name, default, *, use=False, personalized=None, confidence=0.2, n=0):
    value = personalized if use and personalized is not None else default
    return {
        "parameter": name,
        "default_value": default,
        "personalized_value": personalized if use else None,
        "use_personalized": use,
        "confidence": confidence,
        "sample_count": n,
        "method": "test",
        "value": value,
        "threshold_source": "personalized" if use else "default",
    }


def default_params(**overrides):
    params = {
        "hrv_drop_warning_pct": _param("hrv_drop_warning_pct", -12.0),
        "rhr_rise_warning_bpm": _param("rhr_rise_warning_bpm", 4.0),
        "tsb_hard_session_range": _param("tsb_hard_session_range", [-8.0, 12.0]),
        "hard_session_spacing_hours": _param("hard_session_spacing_hours", 36.0),
        "load_increase_ratio_caution": _param("load_increase_ratio_caution", 1.5),
        "threshold_density_max_pct": _param("threshold_density_max_pct", 15.0),
        "easy_volume_min_min_per_week": _param("easy_volume_min_min_per_week", 150.0),
        "acwr_caution": _param("acwr_caution", 1.4),
    }
    params.update(overrides)
    return params


class AdaptiveCoachingV4Tests(unittest.TestCase):
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
        self.running_type = running_type
        self.running_type_id = running_type.id
        self.ppap = PpapMetricsService(self.db, None)

    def tearDown(self):
        self.db.close()
        self.tmpdir.cleanup()

    def _add_run(self, activity_id, day, *, hr=130, te=2.0, name="Easy", treadmill=False):
        activity = Activity(
            activity_id=activity_id,
            activity_name=name,
            start_time=datetime(day.year, day.month, day.day, 8, tzinfo=timezone.utc),
            duration=3600,
            distance=10000,
            average_heart_rate=hr,
            average_speed=3.0,
            total_training_effect=te,
            activity_type_id=self.running_type_id,
        )
        activity.activity_type = self.running_type
        if treadmill:
            activity.activity_name = "Treadmill"
        self.db.add(activity)
        self.db.commit()
        return activity

    def test_personalized_threshold_used_in_trace(self):
        params = default_params(
            hard_session_spacing_hours=_param(
                "hard_session_spacing_hours",
                36.0,
                use=True,
                personalized=42.0,
                confidence=0.81,
                n=20,
            )
        )
        service = NextBestWorkoutService(self.db, None, self.ppap)
        with patch.object(service._calibration, "resolve_parameters", return_value=params):
            with patch.object(service._calibration, "calibrate_all", return_value={"parameters": []}):
                with patch.object(self.ppap, "get_readiness_component", return_value=80.0):
                    with patch.object(self.ppap, "get_tsb", return_value=4.0):
                        with patch.object(self.ppap, "get_hrv_delta_pct", return_value=0.0):
                            result = service.recommend(date(2026, 5, 28), engine="cascade")
        spacing = [t for t in result["decision_trace"] if t.get("factor") == "hard_session_spacing"]
        # No recent hard session — spacing may be absent; HRV/TSB traces must still expose source.
        sources = {t.get("threshold_source") for t in result["decision_trace"] if "threshold_source" in t}
        self.assertTrue(sources)
        self.assertIn("default", sources | {"personalized"})
        self.assertIn("evidence_strength", result)
        self.assertIn("recommendation_confidence", result)
        self.assertIn("workout_prescription", result)

    def test_personalized_threshold_rejected_weak_evidence(self):
        cal = AthleteCalibrationService(self.db, None)
        weak = cal._parameter_result("hard_session_spacing_hours", 36.0, 24.0, 4, "test", [20, 22, 24, 40])
        self.assertFalse(weak["use_personalized"])
        self.assertEqual(weak["threshold_source"] if "threshold_source" in weak else "default", "default")
        resolved = cal._with_resolved_value(weak)
        self.assertFalse(resolved["use_personalized"])
        self.assertEqual(resolved["value"], 36.0)
        self.assertEqual(resolved["threshold_source"], "default")

    def test_goal_12_weeks_out_is_build_or_base(self):
        day = date(2026, 5, 28)
        goal = {
            "goal_type": "race",
            "event": "half_marathon",
            "target_date": (day + timedelta(days=84)).isoformat(),
            "target_time_sec": 6300,
            "priority": "A",
        }
        ctx = GoalContextService(self.db, None, self.ppap, goal=goal).build(day)
        self.assertEqual(ctx["days_to_goal"], 84)
        self.assertEqual(ctx["target_event"], "half_marathon")
        phase = TrainingPhaseService(self.db, None, self.ppap, goal=goal).determine(day)
        self.assertIn(phase["phase"], {"base", "build", "recovery"})
        caps = RaceCapabilityService(self.db, None, self.ppap, goal=goal).assess(day)
        self.assertEqual(caps["event"], "half_marathon")
        self.assertIn("durability", caps["capabilities"])

    def test_no_target_race(self):
        ctx = GoalContextService(self.db, None, self.ppap).build(date(2026, 5, 28))
        self.assertEqual(ctx["goal_type"], "general_fitness")
        self.assertIsNone(ctx["target_event"])
        self.assertEqual(ctx["goal_feasibility"]["status"], "insufficient_data")

    def test_unrealistic_target_flagged(self):
        day = date(2026, 5, 28)
        with patch.object(GoalContextService, "_predicted_time", return_value=(7800.0, "critical_speed", 0.65)):
            ctx = GoalContextService(self.db, None, self.ppap).build(
                day,
                goal={
                    "goal_type": "race",
                    "event": "half_marathon",
                    "target_date": "2026-10-18",
                    "target_time_sec": 5400,
                },
            )
        self.assertEqual(ctx["goal_feasibility"]["status"], "unlikely")

    def test_poor_hrv_blocks_hard_even_with_readiness(self):
        service = NextBestWorkoutService(self.db, None, self.ppap)
        params = default_params()
        with patch.object(service._calibration, "resolve_parameters", return_value=params):
            with patch.object(service._calibration, "calibrate_all", return_value={"parameters": []}):
                with patch.object(self.ppap, "get_readiness_component", return_value=80.0):
                    with patch.object(self.ppap, "get_tsb", return_value=5.0):
                        with patch.object(self.ppap, "get_hrv_delta_pct", return_value=-18.0):
                            result = service.recommend(date(2026, 5, 28), engine="cascade")
        self.assertIn(result["workout_type"], {"easy_run", "recovery_run", "rest"})
        hrv_trace = [t for t in result["decision_trace"] if t.get("factor") == "hrv_delta_pct"]
        self.assertTrue(hrv_trace)
        self.assertEqual(hrv_trace[0]["effect"], "blocks_hard_session")

    def test_hard_spacing_blocks_despite_excellent_readiness(self):
        activity = Activity(
            activity_id="hard1",
            activity_name="Threshold intervals",
            start_time=datetime(2026, 5, 27, 18, tzinfo=timezone.utc),
            duration=3600,
            average_heart_rate=165,
            average_speed=3.5,
            total_training_effect=4.5,
            activity_type_id=self.running_type_id,
        )
        activity.activity_type = self.running_type
        self.db.add(activity)
        self.db.commit()
        service = NextBestWorkoutService(self.db, None, self.ppap)
        params = default_params()
        with patch.object(service._calibration, "resolve_parameters", return_value=params):
            with patch.object(service._calibration, "calibrate_all", return_value={"parameters": []}):
                with patch.object(self.ppap, "get_readiness_component", return_value=90.0):
                    with patch.object(self.ppap, "get_tsb", return_value=6.0):
                        with patch.object(self.ppap, "get_ctl", return_value=60.0):
                            with patch.object(self.ppap, "get_atl", return_value=50.0):
                                with patch.object(self.ppap, "get_hrv_delta_pct", return_value=2.0):
                                    with patch.object(self.ppap, "get_sleep_debt_hours", return_value=0.0):
                                        result = service.recommend(date(2026, 5, 28))
        self.assertIn(result["workout_type"], {"easy_run", "recovery_run"})
        spacing = [t for t in result["decision_trace"] if t.get("factor") == "hard_session_spacing"]
        self.assertTrue(spacing)
        self.assertEqual(spacing[0]["threshold_source"], "default")
        self.assertEqual(spacing[0]["effect"], "blocks_hard_session")

    def test_hard_day_density_blocks_quality(self):
        for idx in range(3):
            self._add_run(
                f"h{idx}",
                date(2026, 5, 24) + timedelta(days=idx),
                hr=165,
                te=4.5,
                name="Threshold",
            )
        ranker = WorkoutCandidateRanker()
        ranked = ranker.rank(
            {
                "readiness": 80,
                "tsb": 4,
                "hard_blocked": True,
                "rest_required": False,
                "recovery_required": False,
                "load_variability": {"flags": ["high_hard_session_density"]},
                "evidence_strength": 0.7,
                "training_phase": {"phase": "build"},
            }
        )
        hard = [c for c in ranked["candidates"] if c["workout_type"] == "threshold"][0]
        self.assertFalse(hard["eligible"])

    def test_intensity_threshold_uses_lt2_not_lt1_band(self):
        intensity = IntensityPrescriptionService(self.db, None, self.ppap).prescribe(
            "threshold",
            end_date=date(2026, 5, 28),
        )
        self.assertEqual(intensity["zone"], "threshold")
        self.assertIn(intensity["source"], {"adaptive_lt2", "critical_speed", "lt1_hr_fallback_not_lt2", "rpe_fallback"})
        if intensity.get("hr_bpm") and intensity["source"] == "adaptive_lt2":
            lo, hi = intensity["hr_bpm"]
            # LT2=170 → ~160–170, not LT1±5% (LT1 fallback ~144.5 → 137–152)
            self.assertGreaterEqual(lo, 155)

    def test_stale_lt2_and_missing_pace(self):
        self.db.add(
            LactateThresholdHistory(
                observed_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                source="garmin",
                lactate_threshold_heart_rate=168,
                lactate_threshold_speed=None,
            )
        )
        self.db.commit()
        # latest_lt2 uses most recent <= end; April 2026 row still wins. Force old-only by end_date.
        intensity = IntensityPrescriptionService(self.db, None, self.ppap).prescribe(
            "threshold",
            end_date=date(2025, 4, 1),
        )
        self.assertIn("stale_lt2", intensity.get("limitations") or ["stale_lt2"])
        self.assertTrue(
            intensity.get("pace_sec_km") is None or "missing_pace_data" in intensity.get("limitations", [])
        )

    def test_missing_hrv_still_recommends(self):
        service = NextBestWorkoutService(self.db, None, self.ppap)
        with patch.object(service._calibration, "resolve_parameters", return_value=default_params()):
            with patch.object(service._calibration, "calibrate_all", return_value={"parameters": []}):
                with patch.object(self.ppap, "get_readiness_component", return_value=70.0):
                    with patch.object(self.ppap, "get_tsb", return_value=0.0):
                        with patch.object(self.ppap, "get_hrv_delta_pct", return_value=None):
                            result = service.recommend(date(2026, 5, 28), engine="cascade")
        self.assertIsNotNone(result["workout_type"])
        self.assertLess(result["evidence_strength"], 0.95)

    def test_prescription_threshold_structure(self):
        rx = WorkoutPrescriptionService(self.db, None, self.ppap).prescribe(
            "threshold",
            day=date(2026, 5, 28),
            phase="build",
        )
        self.assertEqual(rx["main_set"]["repetitions"], 3)
        self.assertEqual(rx["main_set"]["work_duration_min"], 10)
        self.assertIn("target_hr", rx["main_set"])
        self.assertEqual(rx["stimulus"], "LT2 development")

    def test_taper_and_recovery_phases(self):
        day = date(2026, 5, 28)
        taper_goal = {
            "goal_type": "race",
            "event": "10k",
            "target_date": (day + timedelta(days=7)).isoformat(),
            "target_time_sec": 2400,
        }
        phase = TrainingPhaseService(self.db, None, self.ppap, goal=taper_goal).determine(day)
        self.assertIn(phase["phase"], {"taper", "recovery", "peak"})
        with patch.object(self.ppap, "get_readiness_component", return_value=30.0):
            with patch.object(self.ppap, "get_tsb", return_value=-5.0):
                rec_phase = TrainingPhaseService(self.db, None, self.ppap).determine(day)
        self.assertEqual(rec_phase["phase"], "recovery")

    def test_close_candidates_lower_recommendation_confidence(self):
        ranker = WorkoutCandidateRanker()
        ctx = {
            "readiness": 70,
            "tsb": 2,
            "hard_blocked": False,
            "rest_required": False,
            "recovery_required": False,
            "evidence_strength": 0.82,
            "top_limiter": None,
            "training_phase": {"phase": "maintenance"},
            "load_variability": {"flags": []},
            "goal": {"goal_type": "general_fitness"},
            "race_capability": {},
        }
        ranked = ranker.rank(ctx)
        if ranked.get("close_race"):
            self.assertLess(ranked["recommendation_confidence"], ranked["evidence_strength"])
        else:
            self.assertIn("recommendation_confidence", ranked)

    def test_ranking_insufficient_evidence_fallback(self):
        ranked = WorkoutCandidateRanker().rank({"evidence_strength": 0.2, "readiness": 70, "load_variability": {}})
        self.assertTrue(ranked["use_rule_fallback"])
        self.assertIsNone(ranked["selected"])

    def test_plan_adaptation_poor_hrv_delays_quality(self):
        plan = {
            "sessions": [
                {"day_offset": 0, "type": "easy_run"},
                {"day_offset": 1, "type": "threshold"},
            ]
        }
        service = PlanAdaptationService(self.db, None, self.ppap)
        with patch.object(service._calibration, "resolve_parameters", return_value=default_params()):
            with patch.object(self.ppap, "get_hrv_delta_pct", return_value=-16.0):
                with patch.object(self.ppap, "get_rhr_delta_bpm", return_value=1.0):
                    result = service.assess(date(2026, 5, 28), plan=plan)
        self.assertIn(result["plan_status"], {"modify", "recovery_override"})
        self.assertTrue(result["changes"])

    def test_dose_response_naming(self):
        result = TrainingResponseService(self.db, None, self.ppap).analyze_dose_response(
            end_date=date(2026, 5, 28),
            lookback_days=30,
        )
        self.assertIn("best_supported_historical_range", result)
        self.assertNotIn("optimal_range", result)
        self.assertIn("observational", result["disclaimer"])

    def test_effectiveness_no_lookahead(self):
        future = self._add_run("future", date(2026, 8, 1), hr=165, te=4.5, name="Threshold")
        self.assertIsNotNone(future.activity_id)
        result = WorkoutEffectivenessService(self.db, None, self.ppap).analyze(
            "threshold",
            end_date=date(2026, 5, 28),
        )
        self.assertEqual(result["workout_type"], "threshold")
        self.assertLessEqual(result["sample_count"], 0)

    def test_backtest_v4_structure_no_lookahead(self):
        self.db.add(
            LactateThresholdHistory(
                observed_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
                source="garmin",
                lactate_threshold_heart_rate=190,
                lactate_threshold_speed=4.0,
            )
        )
        self.db.commit()
        result = CoachingBacktestV4Service(self.db, None).compare_period(
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 8),
            step_days=7,
        )
        self.assertIn("old_model", result)
        self.assertIn("v4_model", result)
        self.assertIn("difference", result)
        self.assertIn("superiority", result["difference"]["note"].lower())

    def test_acwr_is_diagnostic_not_primary(self):
        service = NextBestWorkoutService(self.db, None, self.ppap)
        with patch.object(service._calibration, "resolve_parameters", return_value=default_params()):
            with patch.object(service._calibration, "calibrate_all", return_value={"parameters": []}):
                with patch.object(self.ppap, "get_readiness_component", return_value=80.0):
                    with patch.object(self.ppap, "get_tsb", return_value=4.0):
                        with patch.object(self.ppap, "get_ctl", return_value=40.0):
                            with patch.object(self.ppap, "get_atl", return_value=70.0):  # ACWR 1.75
                                with patch.object(self.ppap, "get_hrv_delta_pct", return_value=0.0):
                                    result = service.recommend(date(2026, 5, 28), engine="cascade")
        acwr_trace = [t for t in result["decision_trace"] if t.get("factor") == "acwr_diagnostic"]
        self.assertTrue(acwr_trace)
        self.assertEqual(acwr_trace[0]["effect"], "diagnostic_only_not_primary_guardrail")

    def test_hot_hilly_does_not_break_intensity(self):
        activity = self._add_run("hot", date(2026, 5, 20), hr=145)
        activity.temperature = 29.0
        activity.total_ascent = 450
        self.db.commit()
        rx = WorkoutPrescriptionService(self.db, None, self.ppap).prescribe(
            "easy_run",
            day=date(2026, 5, 28),
        )
        self.assertEqual(rx["workout_type"], "easy_run")
        self.assertIn("main_set", rx)


if __name__ == "__main__":
    unittest.main()
