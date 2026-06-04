import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.database.models.activity import Activity, ActivityType, GarminPerformanceMetric
from app.database.models.sleep import Sleep
from app.database.models.lactate_threshold_history import LactateThresholdHistory
from app.mcp import training_tools
from app.services.mcp_derived_metrics_service import DERIVED_METRIC_CATALOG
from app.services.ppap_metrics_service import PpapMetricsService
from app.storage import DataStorage


class McpTrainingToolsTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        engine = create_engine(f"sqlite:///{Path(self.tmpdir.name) / 'test.db'}")
        Base.metadata.create_all(engine)
        self.engine = engine
        self.Session = sessionmaker(bind=engine)
        self.db = self.Session()
        self.storage = DataStorage(str(Path(self.tmpdir.name) / "data"))
        running_type = ActivityType(type_key="running", type_name="Running")
        self.db.add(running_type)
        self.db.commit()
        self.running_type_id = running_type.id

        start = datetime(2026, 5, 28, 8, tzinfo=timezone.utc)
        self.db.add(
            LactateThresholdHistory(
                observed_at=start - timedelta(days=1),
                source="garmin",
                lactate_threshold_heart_rate=166,
                lactate_threshold_speed=3.0,
            )
        )
        self.db.add(
            Activity(
                activity_id="2301",
                activity_name="Morning Run",
                start_time=start,
                duration=1800,
                distance=5000,
                average_heart_rate=145,
                average_speed=2.78,
                training_stress_score=55,
                activity_type_id=self.running_type_id,
            )
        )
        self.db.add(
            GarminPerformanceMetric(
                date=start,
                fitness_age=39.0,
                endurance_score=5100,
                endurance_classification=4,
                hill_score=42.0,
                hill_endurance_score=38.0,
                hill_strength_score=45.0,
            )
        )
        self.db.add(
            Sleep(
                sleep_date=start.date(),
                total_sleep_time=420 * 60.0,
                sleep_score=78.0,
                overall_score=82.0,
                sleep_efficiency=91.0,
                sleep_latency=720.0,
                wake_episodes=3,
                average_heart_rate=48.0,
                lowest_heart_rate=42.0,
                highest_heart_rate=61.0,
                average_respiration_rate=13.2,
                average_spo2=96.0,
                lowest_spo2=93.0,
                stress_score=27.0,
                recovery_score=84.0,
                movement_score=18.0,
                restless_moments=4,
                deep_sleep_percent=21.4,
                light_sleep_percent=52.4,
                rem_sleep_percent=26.2,
                awake_percent=7.1,
                sleep_quality="good",
            )
        )
        self.db.query(Activity).filter_by(activity_id="2301").update(
            {
                "temperature": 16.5,
                "wind_speed": 4.2,
                "wind_direction": 225.0,
                "humidity": 63.0,
                "weather_condition": "partlycloudy_day",
            }
        )
        self.db.commit()
        records = []
        for second in range(0, 1801, 30):
            records.append(
                {
                    "activity_id": 2301,
                    "timestamp": start + timedelta(seconds=second),
                    "distance": 5000 * (second / 1800),
                    "speed": 2.78,
                    "heart_rate": 145,
                    "cadence": 170,
                }
            )
        self.storage.save_activity_details(records)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.tmpdir.cleanup()

    @contextmanager
    def _context(self):
        yield self.db, self.storage

    def test_athlete_profile_and_activity_deep_dive_are_compact_tool_payloads(self):
        with patch.object(training_tools, "training_context", self._context):
            profile = training_tools.athlete_profile()
            deep_dive = training_tools.activity_deep_dive("2301")

        self.assertEqual(profile["latest_threshold"]["lt2_heart_rate_bpm"], 166)
        self.assertEqual(profile["athlete"]["pace_unit"], "min_per_km")
        self.assertEqual(deep_dive["status"], "ok")
        self.assertEqual(deep_dive["activity"]["activity_id"], "2301")
        self.assertEqual(len(deep_dive["kilometer_splits"]), 5)
        self.assertEqual(deep_dive["kilometer_splits"][0]["source"], "details")

    def test_readiness_tool_returns_recommendation_and_flags(self):
        with patch.object(training_tools, "training_context", self._context):
            readiness = training_tools.training_readiness_check("2026-05-28")

        self.assertIn(readiness["recommendation"], {"normal_training", "easy_or_moderate", "easy_or_rest"})
        self.assertIn("banister", readiness)
        self.assertIn("hrv_guidance", readiness)

    def test_metric_catalog_and_timeseries_query_expose_whitelisted_metrics(self):
        with patch.object(training_tools, "training_context", self._context):
            catalog = training_tools.metric_catalog()
            series = training_tools.query_metric_timeseries(
                "activity.training_stress_score",
                start_date="2026-05-01",
                end_date="2026-05-31",
            )

        self.assertIn("activity.training_stress_score", {metric["key"] for metric in catalog["metrics"]})
        self.assertIn("activity.calories", {metric["key"] for metric in catalog["metrics"]})
        self.assertGreater(catalog["count"], 80)
        self.assertEqual(series["status"], "ok")
        self.assertEqual(series["count"], 1)
        self.assertEqual(series["points"][0]["value"], 55.0)

    def test_metric_catalog_exposes_ppap3_metrics(self):
        with patch.object(training_tools, "training_context", self._context):
            catalog = training_tools.metric_catalog()
        keys = {metric["key"] for metric in catalog["metrics"]}
        self.assertEqual(catalog["schema_version"], "ppap-3")
        self.assertIn("readiness.total_score", keys)
        self.assertIn("running.speed_5m_hist", keys)
        self.assertIn("training.class_8_pct", keys)

    def test_metric_catalog_exposes_metric_availability(self):
        with patch.object(training_tools, "training_context", self._context):
            catalog = training_tools.metric_catalog()
        by_key = {metric["key"]: metric for metric in catalog["metrics"]}
        self.assertEqual(by_key["activity.training_stress_score"]["availability"], "supported")
        self.assertEqual(by_key["activity.average_pace"]["availability"], "supported")
        self.assertEqual(by_key["activity.avg_grade_adjusted_speed"]["availability"], "supported")
        self.assertEqual(by_key["activity.grade_adjusted_speed_mps"]["availability"], "supported")
        self.assertEqual(by_key["activity.begin_potential_stamina"]["availability"], "supported")
        self.assertEqual(by_key["activity.end_potential_stamina"]["availability"], "supported")
        self.assertEqual(by_key["activity.min_available_stamina"]["availability"], "supported")
        self.assertEqual(by_key["activity.activity_body_battery_delta"]["availability"], "supported")
        self.assertEqual(by_key["activity.elapsed_duration"]["availability"], "supported")
        self.assertEqual(by_key["activity.max_elevation"]["availability"], "supported")
        self.assertEqual(by_key["activity.min_elevation"]["availability"], "supported")
        self.assertEqual(by_key["activity.moving_duration"]["availability"], "supported")
        self.assertEqual(by_key["activity.total_steps"]["availability"], "supported")
        self.assertEqual(by_key["activity.vo2_max_precise"]["availability"], "supported")
        self.assertEqual(by_key["performance.fitness_age"]["availability"], "supported")
        self.assertEqual(by_key["performance.endurance_score"]["availability"], "supported")
        self.assertEqual(by_key["performance.endurance_classification"]["availability"], "supported")
        self.assertEqual(by_key["performance.hill_score"]["availability"], "supported")
        self.assertEqual(by_key["performance.hill_endurance_score"]["availability"], "supported")
        self.assertEqual(by_key["performance.hill_strength_score"]["availability"], "supported")
        self.assertEqual(by_key["sleep.sleep_score"]["availability"], "supported")
        self.assertEqual(by_key["sleep.sleep_efficiency"]["availability"], "supported")
        self.assertEqual(by_key["sleep.sleep_latency"]["availability"], "supported")
        self.assertEqual(by_key["sleep.wake_episodes"]["availability"], "supported")
        self.assertEqual(by_key["sleep.average_heart_rate"]["availability"], "supported")
        self.assertEqual(by_key["sleep.average_respiration_rate"]["availability"], "supported")
        self.assertEqual(by_key["sleep.average_spo2"]["availability"], "supported")
        self.assertEqual(by_key["sleep.lowest_spo2"]["availability"], "supported")
        self.assertEqual(by_key["sleep.recovery_score"]["availability"], "supported")
        self.assertEqual(by_key["sleep.stress_score"]["availability"], "supported")
        self.assertEqual(by_key["activity.temperature"]["availability"], "supported")
        self.assertEqual(by_key["activity.wind_speed"]["availability"], "supported")
        self.assertEqual(by_key["activity.wind_direction"]["availability"], "supported")
        self.assertEqual(by_key["activity.humidity"]["availability"], "supported")
        self.assertEqual(by_key["activity.weather_condition"]["availability"], "supported")
        self.assertEqual(by_key["running.speed_5m_hist"]["availability"], "computed")
        self.assertEqual(by_key["health.resting_heart_rate"]["availability"], "empty_source")
        self.assertIn("availability_states", catalog)

    def test_eight_training_classes_and_recovery_hours(self):
        service = PpapMetricsService(self.db, self.storage)
        self.assertEqual(service.hr_to_training_class(120, lt1=140, lt2=170, hr_max=185), 1)
        self.assertIn("readiness.total_score", DERIVED_METRIC_CATALOG)
        with patch.object(service, "get_readiness_component", return_value=40.0):
            with patch.object(service, "get_tsb", return_value=-20.0):
                with patch.object(service, "get_hrv_delta_pct", return_value=-10.0):
                    hours = service.get_predicted_recovery_hours(datetime(2026, 5, 28).date())
        self.assertGreaterEqual(hours, 6.0)
        self.assertLessEqual(hours, 120.0)


    def test_metric_catalog_has_glossary_summary(self):
        with patch.object(training_tools, "training_context", self._context):
            catalog = training_tools.metric_catalog()
        self.assertEqual(catalog.get("schema_version"), "ppap-3")
        entry = next(m for m in catalog["metrics"] if m["key"] == "readiness.total_score")
        self.assertIn("summary", entry)

    def test_metric_glossary_entry(self):
        g = training_tools.metric_glossary(metric_key="readiness.total_score")
        self.assertEqual(g["status"], "ok")
        self.assertIn("TrainingReadinessService", g["entry"]["definition"])


if __name__ == "__main__":
    unittest.main()
