import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.database.models.body_battery import BodyBattery
from app.database.models.activity import Activity, ActivityType, GarminPerformanceMetric
from app.database.models.sleep import HRV, RestingHeartRate, Sleep
from app.database.models.stress import Stress
from app.database.models.lactate_threshold_history import LactateThresholdHistory
from app.mcp import training_tools
from app.services.hrv_fetch import LOCAL_DB_HRV_REASON, NO_HRV_ACTIVITY_DAY_REASON
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
        self.db.add(
            HRV(
                measurement_date=start.date(),
                measurement_time=start,
                rmssd=34.0,
                measurement_type="during_sleep",
                status="balanced",
            )
        )
        self.db.add(
            HRV(
                measurement_date=(start - timedelta(days=1)).date(),
                measurement_time=start - timedelta(days=1),
                rmssd=40.0,
                measurement_type="during_sleep",
            )
        )
        self.db.add(
            HRV(
                measurement_date=(start - timedelta(days=2)).date(),
                measurement_time=start - timedelta(days=2),
                rmssd=38.0,
                measurement_type="during_sleep",
            )
        )
        self.db.add(
            RestingHeartRate(
                measurement_date=start.date(),
                measurement_time=start,
                resting_heart_rate=47.0,
            )
        )
        self.db.add(
            BodyBattery(
                date=start.date(),
                max_body_battery=88.0,
                min_body_battery=41.0,
                net_charge=12.0,
            )
        )
        self.db.add(
            Stress(
                stress_date=start.date(),
                stress_level=32.0,
                high_stress_time=5400.0,
                rest_time=28800.0,
            )
        )
        self.db.query(Activity).filter_by(activity_id="2301").update(
            {
                "temperature": 16.5,
                "wind_speed": 4.2,
                "wind_direction": 225.0,
                "humidity": 63.0,
                "weather_condition": "partlycloudy_day",
                "body_battery_start": 72.0,
                "activity_body_battery_delta": -18.0,
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
        self.assertEqual(deep_dive["recovery_context"]["hrv"]["rmssd"], 34.0)
        self.assertEqual(deep_dive["recovery_context"]["hrv"]["source"], "local_db")
        self.assertEqual(deep_dive["recovery_context"]["hrv"]["availability"], "supported")
        self.assertIn("reason", deep_dive["recovery_context"]["hrv"])
        self.assertEqual(deep_dive["recovery_context"]["sleep"]["overall_score"], 82.0)
        self.assertEqual(deep_dive["recovery_context"]["sleep"]["source"], "local_db")
        self.assertEqual(deep_dive["recovery_context"]["resting_heart_rate"]["value"], 47.0)
        self.assertEqual(deep_dive["recovery_context"]["resting_heart_rate"]["availability"], "supported")
        self.assertEqual(deep_dive["recovery_context"]["garmin_performance"]["source"], "local_db")
        body_battery = deep_dive["recovery_context"]["body_battery"]
        self.assertEqual(body_battery["start"]["value"], 72.0)
        self.assertEqual(body_battery["start"]["availability"], "estimated")
        self.assertEqual(body_battery["start"]["source"], "activity_db")
        self.assertEqual(body_battery["delta"]["value"], -18.0)
        self.assertEqual(body_battery["delta"]["availability"], "supported")
        self.assertEqual(body_battery["delta"]["source"], "garmin_activity_summary")
        self.assertEqual(body_battery["end_derived"]["value"], 54.0)
        self.assertEqual(body_battery["daily_max"], 88.0)
        self.assertEqual(body_battery["daily_source"], "local_db")
        self.assertEqual(body_battery["daily_availability"], "supported")
        recovery = deep_dive["activity"]["recovery"]
        self.assertEqual(recovery["body_battery_start"]["value"], 72.0)
        self.assertEqual(recovery["activity_body_battery_delta"]["value"], -18.0)

    def test_mcp_hrv_recovery_context_uses_shared_contract(self):
        with patch.object(training_tools, "training_context", self._context):
            deep_dive = training_tools.activity_deep_dive("2301")

        hrv = deep_dive["recovery_context"]["hrv"]
        self.assertEqual(hrv["source"], "local_db")
        self.assertEqual(hrv["live_status"], "not_attempted")
        self.assertEqual(hrv["availability"], "supported")
        self.assertEqual(hrv["reason"], LOCAL_DB_HRV_REASON)

    def test_mcp_hrv_recovery_context_missing_uses_shared_contract(self):
        self.db.query(HRV).delete()
        self.db.commit()

        with patch.object(training_tools, "training_context", self._context):
            deep_dive = training_tools.activity_deep_dive("2301")

        hrv = deep_dive["recovery_context"]["hrv"]
        self.assertIsNone(hrv["rmssd"])
        self.assertEqual(hrv["source"], "none")
        self.assertEqual(hrv["live_status"], "not_attempted")
        self.assertEqual(hrv["availability"], "missing")
        self.assertEqual(hrv["reason"], NO_HRV_ACTIVITY_DAY_REASON)

    def test_activity_recovery_fields_expose_availability_and_sources(self):
        with patch.object(training_tools, "training_context", self._context):
            deep_dive = training_tools.activity_deep_dive("2301")

        recovery_context = deep_dive["recovery_context"]
        for section in ("hrv", "sleep", "resting_heart_rate", "stress"):
            self.assertIn("source", recovery_context[section])
            self.assertIn("availability", recovery_context[section])
            self.assertIn("reason", recovery_context[section])
        self.assertIn("daily_reason", recovery_context["body_battery"])
        self.assertIn("reason", recovery_context["garmin_performance"])

        readiness = recovery_context["training_readiness"]
        self.assertIn(readiness["availability"], {"stored", "computed", "missing"})
        self.assertIn(readiness["source"], {"activity_db", "training_readiness_service", "none"})
        if readiness["availability"] == "computed":
            self.assertIn("components", readiness)

    def test_body_battery_start_unavailable_sentinel_is_explicit(self):
        self.db.query(Activity).filter_by(activity_id="2301").update({"body_battery_start": -1.0})
        self.db.commit()

        with patch.object(training_tools, "training_context", self._context):
            deep_dive = training_tools.activity_deep_dive("2301")

        start = deep_dive["recovery_context"]["body_battery"]["start"]
        self.assertIsNone(start["value"])
        self.assertEqual(start["availability"], "unavailable")
        self.assertEqual(start["source"], "none")
        self.assertIsNone(deep_dive["recovery_context"]["body_battery"]["end_derived"])

    def test_stored_training_readiness_is_preferred_over_computed(self):
        self.db.query(Activity).filter_by(activity_id="2301").update({"training_readiness_score": 81.0})
        self.db.commit()

        with patch.object(training_tools, "training_context", self._context):
            deep_dive = training_tools.activity_deep_dive("2301")

        readiness = deep_dive["recovery_context"]["training_readiness"]
        self.assertEqual(readiness["value"], 81.0)
        self.assertEqual(readiness["availability"], "stored")
        self.assertEqual(readiness["source"], "activity_db")
        self.assertNotIn("components", readiness)

    def test_readiness_tool_returns_recommendation_and_flags(self):
        with patch.object(training_tools, "training_context", self._context):
            readiness = training_tools.training_readiness_check("2026-05-28")

        self.assertIn(readiness["recommendation"], {"normal_training", "easy_or_moderate", "easy_or_rest"})
        self.assertIn("banister", readiness)
        self.assertIn("hrv_guidance", readiness)
        self.assertIn("recovery_context", readiness)
        self.assertIn("readiness_composites", readiness)
        self.assertIn("metric_links", readiness)
        self.assertEqual(readiness["recovery_context"]["hrv"]["rmssd"], 34.0)
        self.assertIn("stress", readiness["recovery_context"])

    def test_metric_alias_hrv_rmssd_resolves_in_timeseries(self):
        with patch.object(training_tools, "training_context", self._context):
            canonical = training_tools.query_metric_timeseries(
                "health.hrv_rmssd",
                start_date="2026-05-01",
                end_date="2026-05-31",
            )
            alias = training_tools.query_metric_timeseries(
                "hrv.rmssd",
                start_date="2026-05-01",
                end_date="2026-05-31",
            )

        self.assertEqual(canonical["status"], "ok")
        self.assertEqual(alias["status"], "ok")
        self.assertEqual(alias["requested_metric_key"], "hrv.rmssd")
        self.assertEqual(alias["canonical_key"], "health.hrv_rmssd")
        self.assertEqual(alias["points"], canonical["points"])

    def test_metric_glossary_resolves_alias_key(self):
        g = training_tools.metric_glossary(metric_key="hrv.rmssd")
        self.assertEqual(g["status"], "ok")
        self.assertEqual(g["entry"]["canonical_key"], "health.hrv_rmssd")
        self.assertEqual(g["entry"]["requested_metric_key"], "hrv.rmssd")

    def test_metric_glossary_list_includes_semantic_links(self):
        g = training_tools.metric_glossary()
        self.assertEqual(g["status"], "ok")
        self.assertIn("semantic_links", g)
        self.assertIn("metric_aliases", g)

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
        self.assertEqual(by_key["activity.body_battery_start"]["availability"], "supported")
        self.assertEqual(by_key["activity.training_readiness_score"]["availability"], "supported")
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
        self.assertEqual(by_key["health.resting_heart_rate"]["availability"], "supported")
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

    def test_athlete_profile_hrv_uses_shared_contract(self):
        with patch.object(training_tools, "training_context", self._context):
            profile = training_tools.athlete_profile()

        hrv = profile["latest_hrv"]
        self.assertEqual(hrv["source"], "local_db")
        self.assertEqual(hrv["availability"], "supported")
        self.assertEqual(hrv["rmssd"], 34.0)
        self.assertIn("recovery_tools", profile)

    def test_daily_recovery_context_matches_activity_recovery_sections(self):
        with patch.object(training_tools, "training_context", self._context):
            daily = training_tools.daily_recovery_context("2026-05-28")
            deep_dive = training_tools.activity_deep_dive("2301")

        self.assertEqual(daily["status"], "ok")
        self.assertEqual(daily["date"], "2026-05-28")
        self.assertEqual(daily["hrv"]["rmssd"], deep_dive["recovery_context"]["hrv"]["rmssd"])
        self.assertEqual(daily["stress"]["stress_level"], 32.0)
        self.assertEqual(daily["stress"]["availability"], "supported")
        self.assertIn("metric_links", daily)
        self.assertNotIn("start", daily["body_battery"])

    def test_readiness_snapshot_links_composites_and_recovery(self):
        with patch.object(training_tools, "training_context", self._context):
            snapshot = training_tools.readiness_snapshot("2026-05-28")

        self.assertEqual(snapshot["status"], "ok")
        self.assertIn("composites", snapshot)
        self.assertIn("fitness_ctl", snapshot["composites"])
        self.assertEqual(snapshot["recovery_context"]["date"], "2026-05-28")
        self.assertIn("readiness.total_score", snapshot["metric_links"].values())

    def test_metric_catalog_exposes_semantic_links_and_recovery_tools(self):
        with patch.object(training_tools, "training_context", self._context):
            catalog = training_tools.metric_catalog()

        self.assertIn("semantic_links", catalog)
        self.assertIn("metric_aliases", catalog)
        self.assertIn("recovery_tools", catalog)
        self.assertGreater(catalog["stored_metric_count"], 0)
        self.assertGreater(catalog["derived_metric_count"], 0)
        topics = {link["topic"] for link in catalog["semantic_links"]}
        self.assertIn("Readiness", topics)
        by_key = {metric["key"]: metric for metric in catalog["metrics"]}
        self.assertEqual(by_key["health.hrv_rmssd"]["aliases"], ["hrv.rmssd"])
        self.assertEqual(by_key["hrv.rmssd"]["canonical_key"], "health.hrv_rmssd")

    def test_metric_glossary_search_finds_stored_catalog_key(self):
        result = training_tools.metric_glossary(search="body_battery_delta")
        keys = {entry["metric_key"] for entry in result["entries"]}
        self.assertIn("activity.body_battery_delta", keys)


if __name__ == "__main__":
    unittest.main()
