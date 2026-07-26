"""Tester for dataintegritetskontroll."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.migrations import run_migrations
from app.database.models import Activity, ActivityType
from app.services.data_integrity_service import build_data_integrity_report


class DataIntegrityReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp.name) / "integrity.db"
        url = f"sqlite:///{db_path}"
        self.engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        run_migrations(self.engine, url)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        run_type = ActivityType(type_key="running", type_name="Løping")
        self.db.add(run_type)
        self.db.commit()
        self.run_type_id = run_type.id

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.tmp.cleanup()

    def test_detects_all_issue_types(self):
        now = datetime.now(timezone.utc)
        self.db.add_all(
            [
                Activity(
                    activity_id="missing-date",
                    activity_name="Uten dato",
                    start_time=None,
                    distance=1000,
                ),
                Activity(
                    activity_id="neg-dist",
                    activity_name="Negativ",
                    start_time=now,
                    distance=-100.0,
                    average_pace=300.0,
                ),
                Activity(
                    activity_id="bad-pace",
                    activity_name="Ugyldig pace",
                    start_time=now,
                    distance=5000,
                    average_pace=10.0,  # for raskt
                    average_heart_rate=140,
                    activity_type_id=self.run_type_id,
                ),
                Activity(
                    activity_id="null-hr",
                    activity_name="Uten HR",
                    start_time=now,
                    distance=5000,
                    average_pace=300.0,
                    average_heart_rate=None,
                    activity_type_id=self.run_type_id,
                ),
                Activity(
                    activity_id="no-vo2",
                    activity_name="Uten VO2",
                    start_time=now,
                    distance=5000,
                    average_pace=300.0,
                    average_heart_rate=150,
                    vo2_max=None,
                    activity_type_id=self.run_type_id,
                ),
                # Duplikat-par
                Activity(
                    activity_id="dup-a",
                    activity_name="Dup A",
                    start_time=now,
                    distance=3000,
                    duration=1200,
                    average_heart_rate=130,
                ),
                Activity(
                    activity_id="dup-b",
                    activity_name="Dup B",
                    start_time=now,
                    distance=3000,
                    duration=1200,
                    average_heart_rate=131,
                ),
            ]
        )
        self.db.commit()

        report = build_data_integrity_report(self.db)
        self.assertEqual(report["status"], "unhealthy")
        self.assertGreaterEqual(report["issues"]["missing_dates"]["count"], 1)
        self.assertGreaterEqual(report["issues"]["negative_distances"]["count"], 1)
        self.assertGreaterEqual(report["issues"]["invalid_pace"]["count"], 1)
        self.assertGreaterEqual(report["issues"]["null_hr"]["count"], 1)
        self.assertGreaterEqual(report["issues"]["missing_vo2"]["count"], 1)
        self.assertGreaterEqual(report["issues"]["duplicates"]["group_count"], 1)

    def test_ok_when_clean(self):
        self.db.add(
            Activity(
                activity_id="clean-1",
                activity_name="OK",
                start_time=datetime.now(timezone.utc),
                distance=5000,
                average_pace=300.0,
                average_heart_rate=145,
                vo2_max=50.0,
                activity_type_id=self.run_type_id,
            )
        )
        self.db.commit()
        report = build_data_integrity_report(self.db)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["critical_issue_count"], 0)


if __name__ == "__main__":
    unittest.main()
