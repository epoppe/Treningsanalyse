import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, HRV, Sleep
from app.database.models.activity import Activity, ActivityType, GarminPerformanceMetric
from app.database.models.lactate_threshold_history import LactateThresholdHistory
from app.services.trend_analysis_service import TrendAnalysisService


class TrendAnalysisServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        engine = create_engine(f"sqlite:///{Path(self.tmpdir.name) / 'test.db'}")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        running_type = ActivityType(type_key="running", type_name="Running")
        self.db.add(running_type)
        self.db.commit()
        self.running_type_id = running_type.id
        self.service = TrendAnalysisService(self.db, None)

    def tearDown(self):
        self.db.close()
        self.tmpdir.cleanup()

    def test_vo2max_improving_trend(self):
        base = date(2026, 1, 1)
        for idx in range(10):
            self.db.add(
                GarminPerformanceMetric(
                    date=base + timedelta(days=idx * 7),
                    vo2_max_precise=50.0 + idx * 0.3,
                )
            )
        self.db.commit()
        end = base + timedelta(days=63)
        trend = self.service.analyze_metric("vo2max", end_date=end, window_days=90)
        self.assertGreater(trend["sample_count"], 0)
        self.assertEqual(trend["direction"], "improving")
        self.assertGreater(trend["confidence"], 0)

    def test_empty_series_returns_uncertain(self):
        trend = self.service.analyze_metric("vo2max", end_date=date(2026, 5, 1), window_days=28)
        self.assertEqual(trend["direction"], "uncertain")
        self.assertEqual(trend["confidence"], 0.0)

    def test_few_datapoints_low_confidence(self):
        base = date(2026, 5, 1)
        for idx in range(2):
            self.db.add(
                Sleep(
                    sleep_date=base + timedelta(days=idx),
                    sleep_score=70 + idx,
                )
            )
        self.db.commit()
        trend = self.service.analyze_metric("sleep_score", end_date=base + timedelta(days=1), window_days=7)
        self.assertLessEqual(trend["confidence"], 0.5)

    def test_change_point_detection(self):
        values = list(range(10, 20)) + list(range(30, 40))
        detected = self.service._detect_change_point([float(v) for v in values])
        self.assertTrue(detected)

    def test_no_lookahead_uses_only_past_data(self):
        """Seriedata filtreres av query — ingen fremtidige rader inkludert."""
        observed = date(2026, 3, 1)
        self.db.add(
            LactateThresholdHistory(
                observed_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
                source="garmin",
                lactate_threshold_heart_rate=165,
                lactate_threshold_speed=3.2,
            )
        )
        self.db.add(
            LactateThresholdHistory(
                observed_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
                source="garmin",
                lactate_threshold_heart_rate=170,
                lactate_threshold_speed=3.4,
            )
        )
        self.db.commit()
        series = self.service._lt_series(observed - timedelta(days=30), observed, "hr")
        self.assertEqual(len(series), 1)
        self.assertEqual(series[0][1], 165.0)


if __name__ == "__main__":
    unittest.main()
