"""Grensetester for tre-lags dataarkitektur."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.migrations import run_migrations
from app.database.models import Activity
from app.layers.derived_guard import scan_derived_layer_violations
from app.layers.normalized import load_fit_series, to_normalized_activity
from app.layers.raw_access import parse_raw_fit_records_to_dataframe


class LayerBoundaryTests(unittest.TestCase):
    def test_derived_modules_do_not_read_garmin_json(self):
        app_root = Path(__file__).resolve().parents[1] / "app"
        violations = scan_derived_layer_violations(app_root)
        self.assertEqual(
            violations,
            [],
            msg="Lag 3 leser Garmin JSON direkte:\n"
            + "\n".join(f"{p}:{n} ({pat})" for p, n, pat in violations),
        )

    def test_parse_raw_fit_records(self):
        df = parse_raw_fit_records_to_dataframe(
            {
                "records": [
                    {
                        "timestamp": "2024-01-01T10:00:00Z",
                        "speed": 3.0,
                        "heart_rate": 140,
                        "distance": 100,
                    },
                    {
                        "timestamp": "2024-01-01T10:00:05Z",
                        "enhanced_speed": 3.1,
                        "heartrate": 142,
                        "distance": 115,
                    },
                ]
            }
        )
        self.assertIsNotNone(df)
        self.assertEqual(len(df), 2)
        self.assertIn("speed", df.columns)
        self.assertIn("heart_rate", df.columns)

    def test_normalized_activity_projection(self):
        activity = Activity(
            activity_id="1",
            distance=5000,
            average_speed=3.0,
            average_heart_rate=150,
            vo2_max=50.0,
        )
        norm = to_normalized_activity(activity, has_fit_series=False)
        self.assertEqual(norm.activity_id, "1")
        self.assertEqual(norm.distance, 5000)
        self.assertFalse(hasattr(norm, "detailed_metrics"))


class LoadFitSeriesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp.name) / "layers.db"
        url = f"sqlite:///{db_path}"
        self.engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        run_migrations(self.engine, url)
        self.Session = sessionmaker(bind=self.engine)

        class FakeStorage:
            def __init__(self):
                self._df = None
                self.saved = None

            def get_activity_details(self, activity_id):
                return self._df

            def save_activity_details(self, records, replace_activity_ids=None):
                self.saved = records
                self._df = pd.DataFrame(records)

        self.storage = FakeStorage()

    def tearDown(self):
        self.engine.dispose()
        self.tmp.cleanup()

    def test_materialize_from_raw_when_parquet_missing(self):
        activity = Activity(
            activity_id="42",
            detailed_metrics={
                "records": [
                    {
                        "timestamp": "2024-06-01T08:00:00Z",
                        "speed": 2.5,
                        "heart_rate": 130,
                        "distance": 50,
                    }
                ]
            },
        )
        df = load_fit_series(42, self.storage, activity=activity, allow_raw_materialize=True)
        self.assertIsNotNone(df)
        self.assertFalse(df.empty)
        self.assertIsNotNone(self.storage.saved)


if __name__ == "__main__":
    unittest.main()
