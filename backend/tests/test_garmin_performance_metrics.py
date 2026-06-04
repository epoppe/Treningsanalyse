import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.database.models.activity import Activity, GarminPerformanceMetric
from app.services.sync_service import SyncService
from app.storage import DataStorage


class FakeGarminClient:
    async def initialize(self):
        return True

    async def get_daily_garmin_performance_metrics(self, target_date):
        return {
            "vo2_max": 44.0,
            "vo2_max_precise": 43.8,
            "fitness_age": 39.0,
            "monthly_load_aerobic_high": 2215.1,
            "monthly_load_anaerobic": 186.7,
            "training_balance_feedback_phrase": "AEROBIC_LOW_SHORTAGE",
            "training_status": 7,
            "sport": "RUNNING",
            "daily_training_load_acute": 123.0,
            "endurance_score": 5100,
            "endurance_classification": 4,
            "hill_score": 42,
            "hill_endurance_score": 38.0,
            "hill_strength_score": 45.0,
            "raw_maxmet": {"generic": {"vo2MaxPreciseValue": 43.8}},
        }

    async def get_activity_summary_metrics(self, activity_id):
        return {
            "vo2_max_precise": 43.8,
            "avg_grade_adjusted_speed": 3.1,
            "begin_potential_stamina": 95.0,
            "end_potential_stamina": 61.0,
            "min_available_stamina": 44.0,
            "activity_body_battery_delta": -18.0,
            "training_load": 180.0,
            "aerobic_training_effect": 4.2,
            "anaerobic_training_effect": 1.1,
            "training_effect_label": "TEMPO",
            "aerobic_training_effect_message": "AEROBIC_HIGHLY_IMPACTING",
            "moving_duration": 2800.0,
            "elapsed_duration": 2900.0,
            "min_elevation": 10.0,
            "max_elevation": 95.0,
        }


class GarminPerformanceMetricsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        engine = create_engine(f"sqlite:///{Path(self.tmpdir.name) / 'test.db'}")
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)
        self.db = self.Session()
        self.storage = DataStorage(str(Path(self.tmpdir.name) / "data"))
        self.service = SyncService(FakeGarminClient(), self.storage, self.db)

    def tearDown(self):
        self.db.close()
        self.tmpdir.cleanup()

    async def test_daily_garmin_performance_metrics_are_persisted(self):
        start = datetime(2026, 5, 27, tzinfo=timezone.utc)
        result = await self.service.sync_garmin_performance_metrics(
            start,
            start,
            force_refresh_recent=True,
            ignore_sync_state=True,
        )

        self.assertEqual(result["updated_count"], 1)
        row = self.db.query(GarminPerformanceMetric).one()
        self.assertEqual(row.vo2_max, 44.0)
        self.assertEqual(row.vo2_max_precise, 43.8)
        self.assertEqual(row.fitness_age, 39.0)
        self.assertEqual(row.training_balance_feedback_phrase, "AEROBIC_LOW_SHORTAGE")
        self.assertEqual(row.training_status, 7)
        self.assertEqual(row.endurance_score, 5100)
        self.assertEqual(row.endurance_classification, 4)
        self.assertEqual(row.hill_score, 42)
        self.assertEqual(row.hill_endurance_score, 38.0)
        self.assertEqual(row.hill_strength_score, 45.0)

    async def test_activity_summary_metrics_are_persisted_during_training_effect_sync(self):
        self.db.add(
            Activity(
                activity_id="23032886495",
                activity_name="Oslo Loping",
                start_time=datetime(2026, 5, 27, 14, 39, tzinfo=timezone.utc),
                distance=8776,
                duration=2855,
            )
        )
        self.db.commit()

        result = await self.service.sync_training_effect_data(
            datetime(2026, 5, 27, tzinfo=timezone.utc),
            datetime(2026, 5, 28, tzinfo=timezone.utc),
            force_refresh_recent=True,
            ignore_sync_state=True,
        )

        self.assertEqual(result["updated_count"], 1)
        activity = self.db.query(Activity).filter_by(activity_id="23032886495").one()
        self.assertEqual(activity.vo2_max_precise, 43.8)
        self.assertEqual(activity.avg_grade_adjusted_speed, 3.1)
        self.assertEqual(activity.begin_potential_stamina, 95.0)
        self.assertEqual(activity.end_potential_stamina, 61.0)
        self.assertEqual(activity.min_available_stamina, 44.0)
        self.assertEqual(activity.activity_body_battery_delta, -18.0)
        self.assertEqual(activity.epoc, 180.0)
        self.assertEqual(activity.total_training_effect, 4.2)
        self.assertEqual(activity.total_anaerobic_training_effect, 1.1)
        self.assertEqual(activity.training_effect_label, "TEMPO")
        self.assertEqual(activity.moving_duration, 2800.0)
        self.assertEqual(activity.elapsed_duration, 2900.0)
        self.assertEqual(activity.min_elevation, 10.0)
        self.assertEqual(activity.max_elevation, 95.0)

    def test_apply_activity_summary_metrics_persists_duration_and_elevation(self):
        activity = Activity(
            activity_id="111",
            activity_name="Test",
            start_time=datetime(2026, 5, 27, 6, 30, tzinfo=timezone.utc),
            duration=3600.0,
        )
        self.db.add(activity)
        self.db.commit()

        changed = self.service._apply_activity_summary_metrics(
            activity,
            {
                "moving_duration": 3500.0,
                "elapsed_duration": 3665.0,
                "min_elevation": 42.5,
                "max_elevation": 128.0,
            },
        )

        self.assertTrue(changed)
        self.assertEqual(activity.moving_duration, 3500.0)
        self.assertEqual(activity.elapsed_duration, 3665.0)
        self.assertEqual(activity.min_elevation, 42.5)
        self.assertEqual(activity.max_elevation, 128.0)

    def test_apply_activity_summary_metrics_normalizes_stride_and_ground_contact(self):
        activity = Activity(
            activity_id="112",
            activity_name="Test",
            start_time=datetime(2026, 5, 27, 6, 30, tzinfo=timezone.utc),
            duration=3600.0,
        )
        self.db.add(activity)
        self.db.commit()

        changed = self.service._apply_activity_summary_metrics(
            activity,
            {
                "stride_length": 120.0,
                "ground_contact_time": 0.25,
            },
        )

        self.assertTrue(changed)
        self.assertEqual(activity.stride_length, 1.2)
        self.assertEqual(activity.ground_contact_time, 250.0)

    @patch("app.services.training_stress_service.TrainingStressService")
    async def test_training_effect_sync_triggers_tss_refresh_when_epoc_differs(
        self, mock_tss_cls
    ):
        mock_tss_cls.return_value.calculate_tss_for_activity.return_value = 180.0
        self.db.add(
            Activity(
                activity_id="23032886496",
                activity_name="Test løp",
                start_time=datetime(2026, 5, 27, 14, 39, tzinfo=timezone.utc),
                distance=5000,
                duration=1800,
                training_stress_score=55.0,
            )
        )
        self.db.commit()

        await self.service.sync_training_effect_data(
            datetime(2026, 5, 27, tzinfo=timezone.utc),
            datetime(2026, 5, 28, tzinfo=timezone.utc),
            force_refresh_recent=True,
            ignore_sync_state=True,
        )

        refreshed = self.service.metrics_service.refresh_metrics_after_te_sync(
            datetime(2026, 5, 27, tzinfo=timezone.utc),
            datetime(2026, 5, 28, tzinfo=timezone.utc),
        )
        activity = self.db.query(Activity).filter_by(activity_id="23032886496").one()
        self.assertEqual(activity.epoc, 180.0)
        self.assertEqual(refreshed["tss_refreshed"], 1)
        self.assertEqual(activity.training_stress_score, 180.0)


if __name__ == "__main__":
    unittest.main()
