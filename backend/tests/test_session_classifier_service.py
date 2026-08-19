import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.database.models.activity import Activity, ActivityLap, ActivityType
from app.database.models.lactate_threshold_history import LactateThresholdHistory
from app.services.session_classifier_service import SessionClassifierService
from app.storage import DataStorage


class SessionClassifierServiceTests(unittest.TestCase):
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
        self.storage = DataStorage(str(Path(self.tmpdir.name) / "data"))
        self.db.add(
            LactateThresholdHistory(
                observed_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
                source="garmin",
                lactate_threshold_heart_rate=170,
                lactate_threshold_speed=3.5,
            )
        )
        self.db.commit()
        self.service = SessionClassifierService(self.db, self.storage)
        self.lt1 = 170 * 0.85
        self.lt2 = 170

    def tearDown(self):
        self.db.close()
        self.tmpdir.cleanup()

    def _run(
        self,
        activity_id: str,
        *,
        hr: int,
        duration_s: int = 3600,
        name: str = "Run",
        te: float | None = None,
        laps: list | None = None,
    ) -> Activity:
        start = datetime(2026, 5, 20, 8, tzinfo=timezone.utc)
        activity = Activity(
            activity_id=activity_id,
            activity_name=name,
            start_time=start,
            duration=duration_s,
            distance=duration_s * 3.0,
            average_heart_rate=hr,
            average_speed=3.0,
            total_training_effect=te,
            activity_type_id=self.running_type_id,
        )
        activity.activity_type = self.running_type
        self.db.add(activity)
        if laps:
            for lap_number, lap_hr, lap_duration in laps:
                self.db.add(
                    ActivityLap(
                        activity_id=activity_id,
                        lap_number=lap_number,
                        duration=lap_duration,
                        average_heart_rate=lap_hr,
                    )
                )
        self.db.commit()

        records = []
        for second in range(0, duration_s + 1, 30):
            records.append(
                {
                    "activity_id": int(activity_id),
                    "timestamp": start + timedelta(seconds=second),
                    "distance": 3.0 * second,
                    "speed": 3.0,
                    "heart_rate": hr,
                    "cadence": 170,
                }
            )
        self.storage.save_activity_details(records)
        return activity

    def test_classifies_threshold_session(self):
        activity = self._run("1001", hr=162, te=4.0)
        result = self.service.classify_activity(
            activity,
            lt1_hr=self.lt1,
            lt2_hr=self.lt2,
        )
        self.assertEqual(result["session_type"], "threshold")
        self.assertGreaterEqual(result["confidence"], 0.6)
        self.assertTrue(any("LT1" in e or "between" in e for e in result["evidence"]))

    def test_classifies_recovery_run(self):
        activity = self._run("1002", hr=115, te=1.5, duration_s=2400)
        result = self.service.classify_activity(
            activity,
            lt1_hr=self.lt1,
            lt2_hr=self.lt2,
        )
        self.assertEqual(result["session_type"], "recovery_run")

    def test_classifies_vo2_intervals_from_laps(self):
        laps = [
            (1, 175, 180),
            (2, 130, 120),
            (3, 176, 180),
            (4, 128, 120),
            (5, 177, 180),
            (6, 125, 120),
        ]
        activity = self._run("1003", hr=155, te=4.2, laps=laps)
        result = self.service.classify_activity(
            activity,
            lt1_hr=self.lt1,
            lt2_hr=self.lt2,
        )
        self.assertIn(result["session_type"], {"vo2_intervals", "mixed", "threshold"})

    def test_classifies_race_from_name(self):
        activity = self._run("1004", hr=175, te=5.0, name="Oslo Marathon race")
        result = self.service.classify_activity(
            activity,
            lt1_hr=self.lt1,
            lt2_hr=self.lt2,
        )
        self.assertEqual(result["session_type"], "race")

    def test_missing_data_returns_unknown_or_low_confidence(self):
        activity = Activity(
            activity_id="1005",
            activity_name="Mystery",
            start_time=datetime(2026, 5, 20, tzinfo=timezone.utc),
            duration=1800,
            activity_type_id=self.running_type_id,
        )
        activity.activity_type = self.running_type
        self.db.add(activity)
        self.db.commit()
        result = self.service.classify_activity(activity, lt1_hr=None, lt2_hr=None)
        self.assertIn(result["session_type"], {"unknown", "easy_aerobic", "mixed"})
        self.assertLessEqual(result["confidence"], 0.5)

    def test_non_running_returns_unknown(self):
        cycle_type = ActivityType(type_key="cycling", type_name="Cycling")
        self.db.add(cycle_type)
        self.db.commit()
        activity = Activity(
            activity_id="1006",
            activity_name="Ride",
            start_time=datetime(2026, 5, 20, tzinfo=timezone.utc),
            duration=3600,
            activity_type_id=cycle_type.id,
        )
        activity.activity_type = cycle_type
        result = self.service.classify_activity(activity)
        self.assertEqual(result["session_type"], "unknown")


if __name__ == "__main__":
    unittest.main()
