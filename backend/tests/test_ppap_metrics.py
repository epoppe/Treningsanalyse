import tempfile
import unittest
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, HRV
from app.database.models.activity import Activity, ActivityType
from app.mcp import training_tools
from app.services.mcp_derived_metrics_service import McpDerivedMetricsService
from app.services.ppap_metrics_service import PpapMetricsService
from app.storage import DataStorage


class PpapMetricsTests(unittest.TestCase):
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

        base = datetime(2026, 5, 20, 8, tzinfo=timezone.utc)
        for offset, tss in enumerate([50, 60, 40, 70, 55, 80, 45]):
            day = base + timedelta(days=offset)
            self.db.add(
                Activity(
                    activity_id=f"run-{offset}",
                    activity_name=f"Run {offset}",
                    start_time=day,
                    duration=3600,
                    distance=10000,
                    average_heart_rate=140,
                    average_speed=2.78,
                    training_stress_score=tss,
                    avg_efficiency_factor=0.02 + offset * 0.0001,
                    activity_type_id=self.running_type_id,
                )
            )
        for offset in range(10):
            self.db.add(
                HRV(
                    measurement_date=date(2026, 5, 10) + timedelta(days=offset),
                    rmssd=40.0 + offset,
                )
            )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.tmpdir.cleanup()

    @contextmanager
    def _context(self):
        yield self.db, self.storage

    def test_ppap_ctl_atl_tsb_follows_exponential_smoothing(self):
        service = PpapMetricsService(self.db)
        day = date(2026, 5, 26)
        service.ensure_load_series(day)
        load = service.get_load_metrics(day)
        self.assertIsNotNone(load["ctl"])
        self.assertIsNotNone(load["atl"])
        self.assertEqual(load["tsb"], round(load["ctl"] - load["atl"], 1))

    def test_derived_metric_catalog_includes_fitness_ctl(self):
        derived = McpDerivedMetricsService(self.db, self.storage)
        keys = {item["key"] for item in derived.list_metric_definitions()}
        self.assertIn("fitness.ctl", keys)
        self.assertIn("fitness.ef_30d", keys)
        self.assertIn("running.economy_hr", keys)

    def test_mcp_timeseries_fitness_ctl(self):
        with patch.object(training_tools, "training_context", self._context):
            series = training_tools.query_metric_timeseries(
                "fitness.ctl",
                start_date="2026-05-20",
                end_date="2026-05-26",
            )
        self.assertEqual(series["status"], "ok")
        self.assertGreater(series["count"], 0)

    def test_readiness_composites_payload(self):
        derived = McpDerivedMetricsService(self.db, self.storage)
        payload = derived.get_readiness_composites(date(2026, 5, 26))
        self.assertEqual(payload["date"], "2026-05-26")
        self.assertIn("fitness_ctl", payload)
        self.assertIn("readiness_score", payload)

    def test_metric_catalog_schema_version(self):
        with patch.object(training_tools, "training_context", self._context):
            catalog = training_tools.metric_catalog()
        self.assertEqual(catalog["schema_version"], "ppap-3")
        keys = {metric["key"] for metric in catalog["metrics"]}
        self.assertIn("fitness.ctl", keys)
        self.assertIn("activity.avg_efficiency_factor", keys)

if __name__ == "__main__":
    unittest.main()
