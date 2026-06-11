import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.database.models.activity import Activity, ActivityType
from app.routers.analytics import get_critical_speed, get_duration_curve, list_fatigue_resistance
from app.services.performance_metrics_service import PerformanceMetricsService
from app.storage import DataStorage


class PerformanceMetricsTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmpdir.name) / "test.db"
        engine = create_engine(f"sqlite:///{db_path}")
        self.engine = engine
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
        self.engine.dispose()
        self.tmpdir.cleanup()

    def _add_constant_activity(self, activity_id: str, start: datetime, speed_mps: float, active_seconds: int):
        total_seconds = 600 + active_seconds + 2
        self.db.add(
            Activity(
                activity_id=activity_id,
                activity_name=f"Run {activity_id}",
                start_time=start,
                distance=speed_mps * active_seconds,
                duration=total_seconds,
                activity_type_id=self.running_type_id,
            )
        )
        self.db.commit()
        records = []
        for second in range(total_seconds + 1):
            speed = 2.0 if second < 600 else speed_mps
            records.append(
                {
                    "activity_id": int(activity_id),
                    "timestamp": start + timedelta(seconds=second),
                    "distance": speed * second,
                    "speed": speed,
                    "heart_rate": 150,
                    "cadence": 170,
                    "temperature": 12,
                    "altitude": 100.0,
                }
            )
        self.storage.save_activity_details(records)

    def _add_fatigue_activity(self, activity_id: str = "900"):
        start = datetime(2026, 5, 25, 8, 0, tzinfo=timezone.utc)
        total_seconds = 70 * 60
        self.db.add(
            Activity(
                activity_id=activity_id,
                activity_name="Long run",
                start_time=start,
                distance=12000,
                duration=total_seconds,
                activity_type_id=self.running_type_id,
            )
        )
        self.db.commit()
        records = []
        for second in range(total_seconds + 1):
            if second < 10 * 60:
                speed, hr, cadence = 2.8, 140, 168
            elif second < 42 * 60:
                speed, hr, cadence = 3.0, 150, 170
            else:
                speed, hr, cadence = 2.7, 160, 165
            records.append(
                {
                    "activity_id": int(activity_id),
                    "timestamp": start + timedelta(seconds=second),
                    "distance": speed * second,
                    "speed": speed,
                    "heart_rate": hr,
                    "cadence": cadence,
                    "temperature": 12,
                    "altitude": 100.0,
                }
            )
        self.storage.save_activity_details(records)

    def _add_spike_activity(self, activity_id: str, start: datetime, base_speed_mps: float, active_seconds: int):
        """Lang økt med kort GPS-spike som ikke skal påvirke CS."""
        total_seconds = 600 + active_seconds + 2
        self.db.add(
            Activity(
                activity_id=activity_id,
                activity_name=f"Spike run {activity_id}",
                start_time=start,
                distance=base_speed_mps * active_seconds,
                duration=total_seconds,
                activity_type_id=self.running_type_id,
            )
        )
        self.db.commit()
        records = []
        spike_start = 600 + max(0, active_seconds // 2)
        for second in range(total_seconds + 1):
            if second < 600:
                speed = 2.5
            elif spike_start <= second < spike_start + 5:
                speed = 15.0
            else:
                speed = base_speed_mps
            records.append(
                {
                    "activity_id": int(activity_id),
                    "timestamp": start + timedelta(seconds=second),
                    "distance": speed * second,
                    "speed": speed,
                    "heart_rate": 150,
                    "cadence": 170,
                    "temperature": 12,
                    "altitude": 100.0,
                }
            )
        self.storage.save_activity_details(records)

    def test_kmh_fit_speed_is_normalized_using_activity_average_speed(self):
        start = datetime(2026, 4, 1, 8, 0, tzinfo=timezone.utc)
        avg_speed_mps = 3.0
        self.db.add(
            Activity(
                activity_id="8001",
                activity_name="Kmh parquet",
                start_time=start,
                distance=avg_speed_mps * 1200,
                duration=1200 + 600,
                average_speed=avg_speed_mps,
                activity_type_id=self.running_type_id,
            )
        )
        self.db.commit()
        records = []
        for second in range(1200 + 600 + 1):
            speed_kmh = 10.8 if second >= 600 else 6.0
            records.append(
                {
                    "activity_id": 8001,
                    "timestamp": start + timedelta(seconds=second),
                    "distance": (speed_kmh / 3.6) * second,
                    "speed": speed_kmh,
                    "heart_rate": 150,
                    "cadence": 170,
                    "temperature": 12,
                    "altitude": 100.0,
                }
            )
        self.storage.save_activity_details(records)
        for idx, duration_s in enumerate([360, 720, 1800], start=1):
            self._add_constant_activity(str(8100 + idx), start + timedelta(days=idx), 3.1, duration_s)

        service = PerformanceMetricsService(self.db, self.storage)
        result = service.calculate_critical_speed(days=None)

        self.assertIsNotNone(result["critical_speed_mps"])
        self.assertLess(result["critical_speed_mps"], 5.0)
        for effort in result["efforts"]:
            self.assertLess(effort["speed_mps"], 7.0)

    def test_gps_spike_is_filtered_from_critical_speed(self):
        start = datetime(2017, 8, 19, 10, 0, tzinfo=timezone.utc)
        self._add_spike_activity("7001", start, 3.2, 180)
        for idx, duration_s in enumerate([360, 720, 1200, 1800], start=2):
            speed = 3.0 + (1800 - duration_s) / 1800 * 0.5
            self._add_constant_activity(str(5000 + idx), start + timedelta(days=idx), speed, duration_s)

        service = PerformanceMetricsService(self.db, self.storage)
        result = service.calculate_critical_speed(days=None)

        self.assertIsNotNone(result["critical_speed_mps"])
        self.assertLess(result["critical_speed_mps"], 6.0)
        for effort in result["efforts"]:
            if effort["duration_seconds"] == 180:
                self.assertLess(effort["speed_mps"], 8.0)

    def test_critical_speed_linear_model_is_estimated_from_best_efforts(self):
        cs = 3.0
        d_prime = 300.0
        start = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
        for idx, duration_s in enumerate([180, 360, 720, 1200, 1800], start=1):
            speed = (cs * duration_s + d_prime) / duration_s
            self._add_constant_activity(str(1000 + idx), start + timedelta(days=idx), speed, duration_s)

        service = PerformanceMetricsService(self.db, self.storage)
        result = service.calculate_critical_speed()

        self.assertAlmostEqual(result["critical_speed_mps"], 3.0, places=1)
        self.assertAlmostEqual(result["d_prime"], 300.0, delta=80)
        self.assertGreaterEqual(result["model_r2"], 0.9)

    def test_duration_curve_returns_best_speed_points(self):
        start = datetime(2026, 2, 1, 8, 0, tzinfo=timezone.utc)
        self._add_constant_activity("2001", start, 3.0, 1200)
        self._add_constant_activity("2002", start + timedelta(days=1), 4.0, 300)

        service = PerformanceMetricsService(self.db, self.storage)
        curve = service.build_duration_curve()

        speed_points = curve["curves"]["speed"]
        self.assertTrue(any(p["duration_seconds"] == 300 and p["speed_mps"] >= 3.9 for p in speed_points))
        self.assertTrue(any(p["duration_seconds"] == 1200 and p["speed_mps"] >= 2.9 for p in speed_points))

    def test_duration_curve_estimates_power_when_raw_column_missing(self):
        start = datetime(2026, 2, 10, 8, 0, tzinfo=timezone.utc)
        self._add_constant_activity("2101", start, 3.5, 600)

        service = PerformanceMetricsService(self.db, self.storage)
        efforts = service.collect_best_efforts(days=None)
        power_efforts = [effort for effort in efforts if effort.get("metric_type") == "power"]
        curve = service.build_duration_curve()

        self.assertGreater(len(power_efforts), 0)
        self.assertTrue(
            any(
                point["duration_seconds"] == 300 and point["power_watts"] > 0
                for point in curve["curves"]["power"]
            )
        )

    def test_fatigue_resistance_is_persisted_per_long_activity(self):
        self._add_fatigue_activity("900")
        activity = self.db.query(Activity).filter_by(activity_id="900").first()
        service = PerformanceMetricsService(self.db, self.storage)

        result = service.calculate_fatigue_resistance_for_activity(activity)

        self.assertIsNotNone(result)
        self.assertLess(result["fatigue_resistance_score"], 100)
        self.assertGreater(result["pace_drop_pct"], 0)
        self.assertGreater(result["hr_drift_pct"], 0)
        self.assertGreater(result["ef_drop_pct"], 0)

        self.db.refresh(activity)
        self.assertIsNotNone(activity.fatigue_resistance_score)

    def test_recalculate_performance_snapshots_persists_critical_speed_and_duration_curve(self):
        start = datetime(2026, 3, 1, 8, 0, tzinfo=timezone.utc)
        for idx, duration_s in enumerate([180, 360, 720], start=1):
            self._add_constant_activity(str(3000 + idx), start + timedelta(days=idx), 3.2, duration_s)

        service = PerformanceMetricsService(self.db, self.storage)
        result = service.recalculate_performance_snapshots()

        self.assertIn("critical_speed", result)
        self.assertIn("duration_curve", result)
        cs_payload = service.get_snapshot_payload("critical_speed")
        self.assertIsNotNone(cs_payload)
        self.assertIn("outdoor", cs_payload)
        self.assertIn("with_treadmill", cs_payload)
        self.assertIsNotNone(service.get_snapshot_payload("duration_curve"))

    def test_analytics_endpoints_return_persisted_performance_metrics(self):
        self._add_fatigue_activity("901")
        activity = self.db.query(Activity).filter_by(activity_id="901").first()
        service = PerformanceMetricsService(self.db, self.storage)
        service.calculate_fatigue_resistance_for_activity(activity)
        service.recalculate_performance_snapshots()

        fatigue = list_fatigue_resistance(limit=10, db=self.db)
        critical_speed = get_critical_speed(db=self.db, storage=self.storage, include_treadmill=False)
        duration_curve = get_duration_curve(db=self.db, storage=self.storage)

        self.assertEqual(fatigue["count"], 1)
        self.assertIn("fatigueResistanceScore", fatigue["activities"][0])
        self.assertIn("critical_speed_mps", critical_speed)
        self.assertIn("points", duration_curve)


if __name__ == "__main__":
    unittest.main()
