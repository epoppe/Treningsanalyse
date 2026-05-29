import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.database.models.activity import Activity, ActivityType
from app.routers.activities import get_activity_efficiency_metrics
from app.routers.analytics import list_decoupling_trends, list_efficiency_trends
from app.services.analysis_service import AnalysisService
from app.services.cache_calculation_service import CacheCalculationService
from app.storage import DataStorage


class AdvancedMetricsTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmpdir.name) / "test.db"
        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)
        self.db = self.Session()
        self.storage = DataStorage(str(Path(self.tmpdir.name) / "data"))
        running_type = ActivityType(type_key="running", type_name="Running")
        self.db.add(running_type)
        self.db.commit()
        self.running_type_id = running_type.id

    def tearDown(self):
        self.db.close()
        self.tmpdir.cleanup()

    def _add_activity(
        self,
        activity_id="123",
        speed_multiplier=1.0,
        duration_minutes=41,
        heart_rate_fn=None,
        speed_fn=None,
        total_ascent=None,
    ):
        start = datetime(2026, 5, 25, 10, 0, tzinfo=timezone.utc)
        self.db.add(
            Activity(
                activity_id=activity_id,
                activity_name="Test run",
                start_time=start,
                distance=7200,
                duration=duration_minutes * 60,
                total_ascent=total_ascent,
                activity_type_id=self.running_type_id,
            )
        )
        self.db.commit()

        records = []
        for minute in range(duration_minutes + 1):
            first_half = minute < duration_minutes // 2
            hr = heart_rate_fn(minute) if heart_rate_fn else (150 if first_half else 160)
            speed = speed_fn(minute) if speed_fn else (3.0 * speed_multiplier)
            records.append(
                {
                    "activity_id": int(activity_id),
                    "timestamp": start + timedelta(minutes=minute),
                    "distance": minute * 180,
                    "speed": speed,
                    "heart_rate": hr,
                    "cadence": 170,
                    "temperature": 12,
                    "altitude": 100.0,
                }
            )
        self.storage.save_activity_details(records)

    def test_efficiency_factor_persists_avg_median_and_steady_state(self):
        self._add_activity()
        service = AnalysisService(self.storage)

        result = service.calculate_efficiency_metrics(123, self.db)

        self.assertEqual(result["activity_id"], 123)
        self.assertEqual(result["efficiency_factor_unit"], "m_per_s_per_bpm")
        self.assertAlmostEqual(result["first_half_efficiency_factor"], 0.01953, places=5)
        self.assertAlmostEqual(result["second_half_efficiency_factor"], 0.01875, places=5)
        self.assertAlmostEqual(result["aerobic_decoupling_percent"], 4.0, places=2)
        self.assertEqual(result["calculation_method"], "calculated")

        activity = self.db.query(Activity).filter_by(activity_id="123").first()
        self.assertIsNotNone(activity.avg_efficiency_factor)
        self.assertIsNotNone(activity.median_efficiency_factor)
        self.assertIsNotNone(activity.steady_state_efficiency_factor)
        self.assertIsNotNone(activity.efficiency_data_quality)
        self.assertAlmostEqual(activity.decoupling_percent, 4.0, places=2)

    def test_decoupling_formula_uses_first_minus_second_over_first(self):
        self._add_activity(activity_id="200")
        service = AnalysisService(self.storage)
        result = service.calculate_efficiency_metrics(200, self.db)

        ef_first = result["first_half_efficiency_factor"]
        ef_second = result["second_half_efficiency_factor"]
        expected = ((ef_first - ef_second) / ef_first) * 100
        self.assertAlmostEqual(result["decoupling_percent"], expected, places=1)

    def test_efficiency_metrics_normalize_legacy_kmh_speed(self):
        self._add_activity(activity_id="456", speed_multiplier=3.6)
        service = AnalysisService(self.storage)

        result = service.calculate_efficiency_metrics(456, self.db)

        self.assertAlmostEqual(result["first_half_speed_mps"], 3.0, places=2)
        self.assertAlmostEqual(result["first_half_efficiency_factor"], 0.01953, places=5)

    def test_decoupling_endpoint_keeps_existing_shape_with_efficiency_context(self):
        self._add_activity(activity_id="789")
        service = AnalysisService(self.storage)

        result = service.calculate_decoupling(789, self.db)

        self.assertAlmostEqual(result["decoupling_percent"], 4.0, places=2)
        self.assertIn("efficiency_factor", result)
        self.assertIn("first_half_efficiency_factor", result)
        self.assertIn("first_half_hr", result)

    def test_efficiency_api_response_returns_both_requested_metrics(self):
        self._add_activity(activity_id="987")

        result = get_activity_efficiency_metrics(987, storage=self.storage, db=self.db)

        self.assertIn("efficiency_factor", result)
        self.assertIn("aerobic_decoupling_percent", result)
        self.assertIn("avg_efficiency_factor", result)
        self.assertAlmostEqual(result["aerobic_decoupling_percent"], 4.0, places=2)

    def test_decoupling_unsuitable_for_short_activity(self):
        self._add_activity(activity_id="301", duration_minutes=25)
        service = AnalysisService(self.storage)
        result = service.calculate_efficiency_metrics(301, self.db)

        self.assertEqual(result["decoupling_suitability_flag"], "unsuitable")
        self.assertIn("too_short", result["decoupling_reason_if_unsuitable"])

    def test_decoupling_unsuitable_for_interval_like_pace(self):
        self._add_activity(
            activity_id="302",
            duration_minutes=50,
            speed_fn=lambda m: 5.0 if m % 2 == 0 else 2.5,
        )
        service = AnalysisService(self.storage)
        result = service.calculate_efficiency_metrics(302, self.db)

        self.assertEqual(result["decoupling_suitability_flag"], "unsuitable")
        self.assertIn("interval_like_pace", result["decoupling_reason_if_unsuitable"])

    def test_decoupling_unsuitable_for_many_stops(self):
        self._add_activity(
            activity_id="303",
            duration_minutes=50,
            speed_fn=lambda m: 0.0 if m % 3 == 0 else 3.0,
        )
        service = AnalysisService(self.storage)
        result = service.calculate_efficiency_metrics(303, self.db)

        self.assertEqual(result["decoupling_suitability_flag"], "unsuitable")
        self.assertIn("too_many_stops", result["decoupling_reason_if_unsuitable"])

    def test_decoupling_unsuitable_for_missing_heart_rate(self):
        self._add_activity(
            activity_id="304",
            duration_minutes=50,
            heart_rate_fn=lambda m: None if m % 2 == 0 else 150,
        )
        service = AnalysisService(self.storage)
        result = service.calculate_efficiency_metrics(304, self.db)

        self.assertEqual(result["decoupling_suitability_flag"], "unsuitable")
        self.assertIn("missing_heart_rate", result["decoupling_reason_if_unsuitable"])

    def test_cache_service_calculates_efficiency_metrics(self):
        self._add_activity(activity_id="306")
        cache_service = CacheCalculationService(self.db, self.storage)

        result = cache_service.calculate_and_cache_activity("306")

        self.assertEqual(result["status"], "success")
        self.assertIn("efficiency", result["calculations"])
        self.assertIn("avg_efficiency_factor", result["calculations"]["efficiency"])

        activity = self.db.query(Activity).filter_by(activity_id="306").first()
        self.assertIsNotNone(activity.avg_efficiency_factor)
        self.assertIsNotNone(activity.decoupling_percent)

    def test_cache_only_missing_includes_efficiency_fields(self):
        activity = Activity(
            activity_id="partial",
            activity_name="Partial",
            start_time=datetime(2026, 5, 1, tzinfo=timezone.utc),
            training_stress_score=50.0,
            running_economy=1.0,
            negative_split_percent=1.0,
            decoupling_percent=5.0,
        )
        self.db.add(activity)
        self.db.commit()

        cache_service = CacheCalculationService(self.db, self.storage)
        stats = cache_service.calculate_and_cache_all_activities(only_missing=True, limit=10)

        self.assertGreaterEqual(stats["total_activities"], 1)

    def test_analytics_endpoints_return_stored_fields(self):
        self._add_activity(activity_id="305")
        service = AnalysisService(self.storage)
        service.calculate_efficiency_metrics(305, self.db)

        efficiency = list_efficiency_trends(limit=10, db=self.db)
        decoupling = list_decoupling_trends(limit=10, db=self.db)

        self.assertEqual(efficiency["count"], 1)
        self.assertEqual(decoupling["count"], 1)
        self.assertIn("avgEfficiencyFactor", efficiency["activities"][0])
        self.assertIn("decouplingPercent", decoupling["activities"][0])
        self.assertIn("decouplingSuitabilityFlag", decoupling["activities"][0])


if __name__ == "__main__":
    unittest.main()
