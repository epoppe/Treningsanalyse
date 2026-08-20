import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.database.models.activity import Activity, ActivityLap, ActivityType
from app.database.models.coaching_v5 import CalibrationSnapshot, RecommendationRecord
from app.services.athlete_feedback_service import AthleteFeedbackService
from app.services.calibration_snapshot_service import CalibrationSnapshotService
from app.services.cross_training_load_service import CrossTrainingLoadService
from app.services.musculoskeletal_readiness_service import MusculoskeletalReadinessService
from app.services.next_best_workout_service import NextBestWorkoutService
from app.services.perceived_load_service import PerceivedLoadService
from app.services.personalization_stability_service import PersonalizationStabilityService
from app.services.plan_adaptation_service import PlanAdaptationService
from app.services.ppap_metrics_service import PpapMetricsService
from app.services.projected_athlete_state_service import ProjectedAthleteStateService
from app.services.recommendation_execution_service import RecommendationExecutionService
from app.services.recommendation_ledger_service import RecommendationLedgerService
from app.services.recommendation_outcome_service import RecommendationOutcomeService
from app.services.training_availability_service import TrainingAvailabilityService
from app.services.training_experiment_service import TrainingExperimentService
from app.services.training_plan_store import TrainingPlanStore
from app.services.weekly_plan_optimizer import WeeklyPlanOptimizer
from app.services.workout_candidate_ranker import WorkoutCandidateRanker
from app.services.workout_execution_analysis_service import WorkoutExecutionAnalysisService


def _rec_payload(**overrides):
    payload = {
        "workout_type": "threshold",
        "recommendation_confidence": 0.72,
        "evidence_strength": 0.7,
        "decision_status": "recommend",
        "decision_trace": [{"factor": "hard_session_spacing", "threshold": 48}],
        "training_phase": {"phase": "build"},
        "goal": {"target_event": "half_marathon", "goal_type": "race"},
        "race_capability": {"primary_gap": "durability"},
        "workout_prescription": {
            "total_duration_min": 55,
            "main_set": {
                "repetitions": 3,
                "work_duration_min": 10,
                "recovery_duration_min": 2,
                "target_hr": [158, 164],
            },
        },
        "candidate_workouts": [
            {"workout_type": "threshold", "ranking_score": 80},
            {"workout_type": "easy_run", "ranking_score": 70},
        ],
        "context_summary": {
            "readiness": 70,
            "tsb": 2,
            "as_of_date": "2026-05-19",
            "lookahead_bound": "2026-05-19",
        },
        "decision_engine": "ranked",
    }
    payload.update(overrides)
    return payload


class AdaptiveCoachingV5Tests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        engine = create_engine(f"sqlite:///{Path(self.tmpdir.name) / 'test.db'}")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.running = ActivityType(type_key="running", type_name="Running")
        self.cycling = ActivityType(type_key="cycling", type_name="Cycling")
        self.strength = ActivityType(type_key="strength_training", type_name="Strength")
        self.swim = ActivityType(type_key="lap_swimming", type_name="Swim")
        self.db.add_all([self.running, self.cycling, self.strength, self.swim])
        self.db.commit()
        self.ppap = PpapMetricsService(self.db, None)
        self.ledger = RecommendationLedgerService(self.db)

    def tearDown(self):
        self.db.close()
        self.tmpdir.cleanup()

    def _activity(self, activity_id, day, *, type_obj=None, duration=3300, hr=160, name="Run", te=3.0, tss=70):
        type_obj = type_obj or self.running
        activity = Activity(
            activity_id=activity_id,
            activity_name=name,
            start_time=datetime(day.year, day.month, day.day, 8, tzinfo=timezone.utc),
            duration=duration,
            distance=10000,
            average_heart_rate=hr,
            average_speed=3.0,
            total_training_effect=te,
            training_stress_score=tss,
            activity_type_id=type_obj.id,
        )
        activity.activity_type = type_obj
        self.db.add(activity)
        self.db.commit()
        return activity

    def test_recommendation_is_immutable_and_versions_preserved(self):
        saved = self.ledger.record_recommendation(
            _rec_payload(),
            as_of_date=date(2026, 5, 19),
            persist=True,
            model_health="healthy",
        )
        self.assertTrue(saved["persisted"])
        original_type = saved["recommended_workout_type"]
        original_hash = saved["config_hash"]
        self.assertEqual(saved["model_version"], "adaptive_coaching_v5")
        self.assertEqual(saved["decision_engine_version"], "5")
        self.assertTrue(saved["provenance"]["config_hash"])
        self.assertNotEqual(saved["provenance"]["config_hash"], saved.get("git_sha"))

        superseded = self.ledger.supersede_recommendation(
            saved["id"],
            _rec_payload(workout_type="easy_run"),
            as_of_date=date(2026, 5, 19),
        )
        self.assertTrue(superseded["original_snapshot_unchanged"])
        original = self.ledger.get_recommendation(saved["id"])
        self.assertEqual(original["recommended_workout_type"], original_type)
        self.assertEqual(original["config_hash"], original_hash)
        self.assertFalse(original["is_active"])
        self.assertEqual(original["superseded_by_id"], superseded["current"]["id"])
        self.assertEqual(superseded["current"]["recommended_workout_type"], "easy_run")

    def test_preview_does_not_persist(self):
        preview = self.ledger.record_recommendation(
            _rec_payload(),
            as_of_date=date(2026, 5, 19),
            persist=False,
        )
        self.assertFalse(preview["persisted"])
        self.assertIsNone(preview["id"])
        self.assertEqual(self.db.query(RecommendationRecord).count(), 0)

    def test_prospective_uses_recorded_not_current_model(self):
        saved = self.ledger.record_recommendation(
            _rec_payload(workout_type="easy_run"),
            as_of_date=date(2026, 5, 19),
            persist=True,
        )
        self._activity("run-1", date(2026, 5, 20), hr=165, name="Threshold", te=4.0)
        outcomes = RecommendationOutcomeService(self.db, None)

        def boom(*_args, **_kwargs):
            raise AssertionError("prospective evaluation must not regenerate current model")

        with patch.object(outcomes._next, "recommend", side_effect=boom):
            result = outcomes.evaluate_recorded_recommendation(saved["id"])
        self.assertEqual(result["evaluation_kind"], "prospective")
        self.assertTrue(result["did_not_regenerate_model"])
        self.assertEqual(result["recommended"], "easy_run")

        backtest = outcomes.simulate_as_of(date(2026, 5, 19))
        self.assertEqual(backtest["evaluation_kind"], "backtest")
        self.assertIn("backtest_not_prospective", backtest["limitations"])

    def test_no_lookahead_in_recorded_input_and_projected_state(self):
        saved = self.ledger.record_recommendation(
            _rec_payload(),
            as_of_date=date(2026, 5, 19),
            persist=True,
        )
        self.assertEqual(saved["input_context"]["as_of_date"], "2026-05-19")
        self.assertEqual(saved["input_context"]["lookahead_bound"], "2026-05-19")

        projector = ProjectedAthleteStateService(self.db, None, self.ppap)
        seen = []

        def tracking_state(day):
            seen.append(day)
            return {"fatigue": {"value": 40}, "recovery": {"value": 70}}

        with patch.object(projector._state, "build_state", side_effect=tracking_state):
            with patch.object(self.ppap, "get_ctl", return_value=40.0) as ctl:
                with patch.object(self.ppap, "get_atl", return_value=35.0):
                    with patch.object(self.ppap, "get_hrv_delta_pct", side_effect=AssertionError("future HRV")):
                        projected = projector.project(
                            date(2026, 5, 19),
                            date(2026, 5, 24),
                            planned_sessions=[{"day_offset": 2, "type": "easy_run"}],
                        )
        self.assertEqual(projected["state_type"], "projected")
        self.assertGreater(projected["uncertainty"], 0.2)
        self.assertEqual(seen, [date(2026, 5, 19)])
        ctl.assert_called_with(date(2026, 5, 19))

    def test_execution_followed_modified_skipped_unplanned(self):
        rec = self.ledger.record_recommendation(_rec_payload(), as_of_date=date(2026, 5, 19), persist=True)
        svc = RecommendationExecutionService(self.db, None)
        followed = self._activity("exact", date(2026, 5, 19), duration=55 * 60, hr=161, name="Threshold", te=3.8)
        with patch.object(svc._classifier, "classify_activity", return_value={"session_type": "threshold"}):
            result = svc.link_activity(followed)
        self.assertEqual(result["execution_status"], "followed")

        rec2 = self.ledger.record_recommendation(_rec_payload(), as_of_date=date(2026, 5, 21), persist=True)
        modified = self._activity("mod", date(2026, 5, 21), duration=40 * 60, hr=150, name="Tempo", te=3.2)
        with patch.object(svc._classifier, "classify_activity", return_value={"session_type": "tempo"}):
            result = svc.link_activity(modified)
        self.assertEqual(result["execution_status"], "modified")
        self.assertIn("Adherence", result["note"])

        skipped = svc.mark_skipped(rec["id"])
        self.assertEqual(skipped["execution_status"], "skipped")

        stray = self._activity("stray", date(2026, 6, 1), name="Unplanned")
        with patch.object(svc._classifier, "classify_activity", return_value={"session_type": "easy_aerobic"}):
            result = svc.link_activity(stray)
        self.assertEqual(result["execution_status"], "unplanned")
        self.assertIsNone(result["recommendation_id"])
        self.assertEqual(rec2["recommended_workout_type"], "threshold")

    def test_workout_execution_analysis_intervals(self):
        activity = self._activity("intervals", date(2026, 5, 19), duration=55 * 60, hr=160)
        for i, dur in enumerate([600, 120, 600, 120, 600], start=1):
            self.db.add(
                ActivityLap(
                    activity_id=activity.activity_id,
                    lap_number=i,
                    duration=dur,
                    average_heart_rate=160 if dur == 600 else 130,
                )
            )
        self.db.commit()
        analysis = WorkoutExecutionAnalysisService(self.db).analyze(
            activity,
            {
                "total_duration_min": 55,
                "main_set": {
                    "repetitions": 3,
                    "work_duration_min": 10,
                    "recovery_duration_min": 2,
                    "target_hr": [158, 164],
                },
            },
        )
        self.assertGreaterEqual(analysis["completion_pct"], 90)
        self.assertGreaterEqual(analysis["target_intensity_pct"], 90)
        self.assertEqual(analysis["distinctions"]["physiological_response"], "not_inferred_here")

    def test_weekly_plan_respects_availability_and_travel(self):
        avail = TrainingAvailabilityService(self.db)
        avail.upsert(weekday="tuesday", available=False, reason="family")
        avail.upsert(weekday="wednesday", available=True, max_duration_min=45)
        avail.upsert(weekday="saturday", available=True, allows_long_run=True, max_duration_min=140)
        avail.upsert(weekday="sunday", available=True, allows_long_run=True, max_duration_min=140)
        avail.upsert(on_date=date(2026, 5, 22), available=False, reason="travel")
        fake = _rec_payload()
        optimizer = WeeklyPlanOptimizer(self.db, None, self.ppap)
        with patch.object(optimizer._next, "recommend", return_value=fake):
            with patch.object(optimizer._rx, "prescribe", return_value={"total_duration_min": 50}):
                plan = optimizer.optimize(date(2026, 5, 18), next_rec=fake)
        by_offset = {s["day_offset"]: s for s in plan["sessions"]}
        # 2026-05-18 is Monday; Tuesday = offset 1 unavailable
        self.assertEqual(by_offset[1]["type"], "rest")
        self.assertLessEqual(max(by_offset[2]["duration_min"]), 45)
        long_days = [s["day_offset"] for s in plan["sessions"] if s["type"] == "long_run"]
        self.assertTrue(all(offset >= 5 for offset in long_days))
        friday = date(2026, 5, 22)
        friday_offset = (friday - date(2026, 5, 18)).days
        self.assertEqual(by_offset[friday_offset]["type"], "rest")
        self.assertIn("scores", plan)
        self.assertIn("goal_alignment", plan["scores"])
        self.assertIn("alternatives", plan)
        hard_offsets = [s["day_offset"] for s in plan["sessions"] if s["type"] in {"threshold", "vo2_intervals", "race_pace"}]
        if len(hard_offsets) >= 2:
            self.assertGreaterEqual(hard_offsets[1] - hard_offsets[0], 2)

    def test_plan_versioning_and_recovery_override(self):
        store = TrainingPlanStore(self.db)
        plan = store.persist_new_plan(
            week_start=date(2026, 5, 18),
            payload={
                "week_objective": "build",
                "sessions": [
                    {"day_offset": 0, "type": "easy_run"},
                    {"day_offset": 1, "type": "threshold"},
                ],
            },
        )
        service = PlanAdaptationService(self.db, None, self.ppap)
        with patch.object(service._calibration, "resolve_parameters", return_value={
            "hrv_drop_warning_pct": {"value": -12.0, "threshold_source": "default"},
            "rhr_rise_warning_bpm": {"value": 4.0, "threshold_source": "default"},
        }):
            with patch.object(self.ppap, "get_hrv_delta_pct", return_value=-16.0):
                with patch.object(self.ppap, "get_rhr_delta_bpm", return_value=6.0):
                    result = service.assess(
                        date(2026, 5, 18),
                        plan={**plan, "sessions": plan["sessions"], "plan_id": plan["plan_id"]},
                        persist=True,
                    )
        self.assertIn(result["plan_status"], {"modify", "recovery_override"})
        self.assertEqual(result["previous_plan_id"], plan["plan_id"])
        self.assertEqual(result["new_plan_id"], plan["plan_id"])
        self.assertEqual(result["version"], 2)
        original = store.get_plan(plan["plan_id"])
        self.assertEqual(original["version"], 2)
        self.assertTrue(original["changes"])

    def test_feedback_optional_and_perceived_load(self):
        activity = self._activity("fb1", date(2026, 5, 19), duration=3600, tss=50)
        perceived = PerceivedLoadService(self.db).analyze(activity)
        self.assertTrue(perceived["feedback_missing"])
        AthleteFeedbackService(self.db).record(
            activity.activity_id,
            rpe=9,
            session_feel="very_hard",
            legs="heavy",
            pain=6,
            motivation=2,
        )
        high = PerceivedLoadService(self.db).analyze(activity)
        self.assertIn("higher_perceived_cost_than_expected", high["flags"])
        normal_act = self._activity("fb2", date(2026, 5, 20), duration=3600, tss=80)
        AthleteFeedbackService(self.db).record(
            normal_act.activity_id,
            rpe=7,
            session_feel="as_expected",
            legs="normal",
            pain=0,
            motivation=4,
        )
        normal = PerceivedLoadService(self.db).analyze(normal_act)
        self.assertNotIn("higher_perceived_cost_than_expected", normal["flags"])

    def test_cross_training_load_profiles(self):
        bike = self._activity("bike", date(2026, 5, 18), type_obj=self.cycling, duration=5400, te=4.0, tss=90, name="Hard ride")
        lift = self._activity("lift", date(2026, 5, 18), type_obj=self.strength, duration=2700, te=3.2, name="Heavy legs")
        swim = self._activity("swim", date(2026, 5, 18), type_obj=self.swim, duration=1800, te=2.0, name="Easy swim")
        cross = CrossTrainingLoadService(self.db)
        bike_load = cross.analyze(bike)
        self.assertEqual(bike_load["cardiovascular_load"], "high")
        self.assertEqual(bike_load["running_specific_load"], "low")
        self.assertEqual(bike_load["interference"]["threshold"], "cardio_fatigue")
        lift_load = cross.analyze(lift)
        self.assertEqual(lift_load["musculoskeletal_load"], "high")
        self.assertEqual(lift_load["interference"]["vo2_intervals"], "musculoskeletal")
        swim_load = cross.analyze(swim)
        self.assertEqual(swim_load["interference"]["easy_run"], "recovery_compatible")

        ms = MusculoskeletalReadinessService(self.db, None, self.ppap)
        AthleteFeedbackService(self.db).record(
            lift.activity_id,
            pain=7,
            rpe=8,
            legs="heavy",
            recorded_at=datetime(2026, 5, 19, 12, tzinfo=timezone.utc),
        )
        assessed = ms.assess(date(2026, 5, 19))
        self.assertEqual(assessed["musculoskeletal_readiness"], "low")
        self.assertIn("pain_above_conservative_threshold", assessed["evidence"])
        self.assertIn("Not a medical", assessed["note"])

    def test_abstention_missing_hrv_degraded_health_and_tie(self):
        service = NextBestWorkoutService(self.db, None, self.ppap)
        with patch.object(service._calibration, "resolve_parameters", return_value={
            "hrv_drop_warning_pct": {"value": -12.0, "threshold_source": "default"},
            "rhr_rise_warning_bpm": {"value": 4.0, "threshold_source": "default"},
            "tsb_hard_session_range": {"value": [-8.0, 12.0], "threshold_source": "default"},
            "hard_session_spacing_hours": {"value": 36.0, "threshold_source": "default"},
            "load_increase_ratio_caution": {"value": 1.5, "threshold_source": "default"},
            "threshold_density_max_pct": {"value": 15.0, "threshold_source": "default"},
            "easy_volume_min_min_per_week": {"value": 150.0, "threshold_source": "default"},
            "acwr_caution": {"value": 1.4, "threshold_source": "default"},
        }):
            with patch.object(service._calibration, "calibrate_all", return_value={"parameters": []}):
                with patch.object(self.ppap, "get_readiness_component", return_value=80.0):
                    with patch.object(self.ppap, "get_tsb", return_value=4.0):
                        with patch.object(self.ppap, "get_hrv_delta_pct", return_value=None):
                            missing = service.recommend(date(2026, 5, 28), engine="cascade")
        self.assertEqual(missing["decision_status"], "abstain")
        self.assertEqual(len(missing["safe_alternatives"]), 2)

        with patch.object(service, "_decision_status", wraps=service._decision_status):
            degraded = NextBestWorkoutService._decision_status(
                {"hrv_delta_pct": 0.0, "readiness": 70, "musculoskeletal": {}},
                {"close_race": False, "ranked_eligible": ["threshold", "easy_run"]},
                "threshold",
                0.7,
                0.7,
                "degraded",
            )
        self.assertEqual(degraded[0], "abstain")
        self.assertEqual(len(degraded[1]), 2)

        tied = NextBestWorkoutService._decision_status(
            {"hrv_delta_pct": 1.0, "readiness": 70, "musculoskeletal": {}},
            {"close_race": True, "ranked_eligible": ["threshold", "easy_run"]},
            "threshold",
            0.7,
            0.6,
            "healthy",
        )
        self.assertEqual(tied[0], "abstain")

    def test_calibration_snapshot_hysteresis(self):
        svc = CalibrationSnapshotService(self.db)
        first = svc._dampen("hrv_drop_warning_pct", -12.0, -12.0, None)
        jumped = svc._dampen(
            "hrv_drop_warning_pct",
            -5.0,
            -12.0,
            {"effective_value": -12.0},
        )
        self.assertEqual(first, -12.0)
        self.assertNotEqual(jumped, -5.0)
        self.assertGreaterEqual(jumped, -12.0 - 12.0 * 0.15 - 0.05)

        row = CalibrationSnapshot(
            parameter="hrv_drop_warning_pct",
            effective_value_json=-12.0,
            default_value_json=-12.0,
            sample_count=20,
            confidence=0.8,
        )
        self.db.add(row)
        self.db.commit()
        stability = PersonalizationStabilityService(self.db).assess(as_of_date=date(2026, 5, 28))
        self.assertIn(stability["status"], {"stable", "watch", "unstable"})

    def test_ranker_uses_prospective_records_when_sample_strong(self):
        prospective = {
            "threshold": {
                "value": 90.0,
                "sample_count": 10,
                "confidence": 0.7,
                "source": "prospective_records",
                "usable": True,
            }
        }
        ranked = WorkoutCandidateRanker().rank(
            {"evidence_strength": 0.7, "readiness": 75, "load_variability": {}, "hard_blocked": False},
            prospective_outcomes=prospective,
        )
        thresh = next(c for c in ranked["candidates"] if c["workout_type"] == "threshold")
        self.assertEqual(thresh["historical_outcome_component"]["source"], "prospective_records")
        self.assertTrue(thresh["historical_outcome_component"]["used_in_ranking"])
        self.assertEqual(thresh["historical_outcome_component"]["sample_count"], 10)

    def test_experiment_requires_explicit_confirmation(self):
        svc = TrainingExperimentService(self.db)
        draft = svc.create(
            hypothesis="1 vs 2 threshold stimuli per week",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 28),
            intervention={"threshold_per_week": 2},
            baseline={"threshold_per_week": 1},
            user_confirmed=False,
        )
        self.assertEqual(draft["status"], "draft")
        self.assertFalse(draft["user_confirmed"])
        with self.assertRaises(PermissionError):
            svc.start(draft["id"], user_confirmed=False)
        started = svc.start(draft["id"], user_confirmed=True)
        self.assertEqual(started["status"], "active")
        self.assertTrue(started["user_confirmed"])


if __name__ == "__main__":
    unittest.main()
