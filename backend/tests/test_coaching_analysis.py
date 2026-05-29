import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, HRV, RestingHeartRate, Sleep
from app.database.models.activity import Activity, ActivityType, AnalyticsSnapshot
from app.database.models.lactate_threshold_history import LactateThresholdHistory
from app.services.coaching_analysis_service import CoachingAnalysisService
from app.storage import DataStorage


class CoachingAnalysisTests(unittest.TestCase):
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

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.tmpdir.cleanup()

    def _add_run(
        self,
        activity_id: str,
        start: datetime,
        duration_s: int,
        hr: int,
        load: float,
        speed_mps: float = 3.0,
    ):
        self.db.add(
            Activity(
                activity_id=activity_id,
                activity_name=f"Run {activity_id}",
                start_time=start,
                duration=duration_s,
                distance=duration_s * speed_mps,
                average_heart_rate=hr,
                average_speed=speed_mps,
                training_stress_score=load,
                activity_type_id=self.running_type_id,
            )
        )
        self.db.commit()
        records = []
        for second in range(0, duration_s + 1, 30):
            records.append(
                {
                    "activity_id": int(activity_id),
                    "timestamp": start + timedelta(seconds=second),
                    "distance": speed_mps * second,
                    "speed": speed_mps,
                    "heart_rate": hr,
                    "cadence": 170,
                }
            )
        self.storage.save_activity_details(records)

    def test_coaching_analysis_detects_threshold_heavy_distribution_and_persists_snapshot(self):
        target = date(2026, 5, 28)
        self.db.add(
            LactateThresholdHistory(
                observed_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
                source="garmin",
                lactate_threshold_heart_rate=166,
                lactate_threshold_speed=3.1,
            )
        )
        self.db.commit()

        for idx in range(8):
            day = target - timedelta(days=idx)
            hr = 150 if idx < 5 else 136
            self._add_run(
                str(1000 + idx),
                datetime(day.year, day.month, day.day, 8, tzinfo=timezone.utc),
                3600,
                hr,
                70,
            )

        service = CoachingAnalysisService(self.db, self.storage)
        result = service.build_coaching_analysis(days=14, end_date=target, persist_snapshot=True)

        self.assertEqual(result["thresholds"]["lt2"]["heart_rate_bpm"], 166)
        self.assertIn("too_little_easy_volume", result["polarized_training"]["flags"])
        self.assertGreater(result["polarized_training"]["percentages"]["threshold"], 15)
        self.assertEqual(result["banister"]["model"], "banister_fitness_fatigue")
        snapshot = self.db.query(AnalyticsSnapshot).filter_by(metric_key="training_coaching").one()
        self.assertEqual(snapshot.payload["period"]["days"], 14)

    def test_hrv_guidance_reduces_intensity_when_recovery_markers_are_low(self):
        target = date(2026, 5, 28)
        for idx in range(30, 7, -1):
            day = target - timedelta(days=idx)
            self.db.add(HRV(measurement_date=day, measurement_time=datetime.combine(day, datetime.min.time()), rmssd=45))
            self.db.add(RestingHeartRate(measurement_date=day, resting_heart_rate=50))
        for idx in range(6, -1, -1):
            day = target - timedelta(days=idx)
            self.db.add(HRV(measurement_date=day, measurement_time=datetime.combine(day, datetime.min.time()), rmssd=36))
            self.db.add(RestingHeartRate(measurement_date=day, resting_heart_rate=56))
            self.db.add(Sleep(sleep_date=day, sleep_score=58))
        self.db.commit()

        service = CoachingAnalysisService(self.db, self.storage)
        result = service.build_coaching_analysis(days=14, end_date=target)

        guidance = result["hrv_guidance"]
        self.assertIn("hrv_below_baseline", guidance["flags"])
        self.assertIn("resting_hr_elevated", guidance["flags"])
        self.assertIn("sleep_low", guidance["flags"])
        self.assertEqual(guidance["recommendation"], "reduce_intensity_or_volume")


if __name__ == "__main__":
    unittest.main()
