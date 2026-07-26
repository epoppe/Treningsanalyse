"""Tester for metrikk-proveniens."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.migrations import run_migrations
from app.database.models import MetricProvenance
from app.services.metric_provenance_service import (
    ALGORITHM_VERSIONS,
    compute_source_hash,
    get_activity_provenance,
    record_activity_metrics_from_results,
    upsert_metric_provenance,
)


class MetricProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp.name) / "prov.db"
        url = f"sqlite:///{db_path}"
        self.engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        run_migrations(self.engine, url)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.tmp.cleanup()

    def test_source_hash_stable(self):
        a = compute_source_hash({"b": 2, "a": 1})
        b = compute_source_hash({"a": 1, "b": 2})
        self.assertEqual(a, b)
        self.assertEqual(len(a), 64)

    def test_upsert_and_get(self):
        upsert_metric_provenance(
            self.db,
            entity_type="activity",
            entity_id="123",
            metric_key="running_economy",
            source_hash="abc",
            quality_status="ok",
        )
        self.db.commit()
        rows = get_activity_provenance(self.db, "123")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["metric_key"], "running_economy")
        self.assertEqual(rows[0]["algorithm_version"], ALGORITHM_VERSIONS["running_economy"])
        self.assertEqual(rows[0]["source_hash"], "abc")

        upsert_metric_provenance(
            self.db,
            entity_type="activity",
            entity_id="123",
            metric_key="running_economy",
            source_hash="def",
            quality_status="degraded",
        )
        self.db.commit()
        self.assertEqual(self.db.query(MetricProvenance).count(), 1)
        rows = get_activity_provenance(self.db, "123")
        self.assertEqual(rows[0]["source_hash"], "def")
        self.assertEqual(rows[0]["quality_status"], "degraded")

    def test_record_from_results(self):
        activity = SimpleNamespace(
            activity_id="999",
            distance=5000,
            duration=1800,
            average_speed=2.8,
            average_heart_rate=145,
            epoc=80.0,
            vo2_max=50.0,
            vo2_max_precise=50.2,
            start_time=datetime.now(timezone.utc),
            detailed_metrics=None,
        )
        recorded = record_activity_metrics_from_results(
            self.db,
            activity,
            {
                "tss_calculated": True,
                "running_economy_calculated": True,
                "decoupling_calculated": False,
                "errors": [],
            },
        )
        self.db.commit()
        self.assertIn("training_stress_score", recorded)
        self.assertIn("running_economy", recorded)
        self.assertEqual(len(get_activity_provenance(self.db, "999")), 2)


if __name__ == "__main__":
    unittest.main()
