"""Tester for restartbar synk (checkpoint / SyncState-fremdrift)."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.migrations import run_migrations
from app.database.models import SyncRun, SyncState
from app.services.sync_run_service import (
    advance_activities_sync_state,
    create_sync_run,
    get_latest_incomplete_sync_run,
    mark_sync_run_started,
    update_sync_run_checkpoint,
)


class SyncCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp.name) / "checkpoint.db"
        self.url = f"sqlite:///{db_path}"
        self.engine = create_engine(
            self.url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        run_migrations(self.engine, self.url)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self):
        self.engine.dispose()
        self.tmp.cleanup()

    def test_advance_activities_sync_state_is_monotonic(self):
        db = self.Session()
        try:
            advance_activities_sync_state(db, date(2024, 1, 10))
            advance_activities_sync_state(db, date(2024, 1, 5))
            state = db.query(SyncState).filter_by(key="activities").one()
            self.assertEqual(state.last_synced_date, date(2024, 1, 10))
            advance_activities_sync_state(db, date(2024, 1, 20))
            db.refresh(state)
            self.assertEqual(state.last_synced_date, date(2024, 1, 20))
        finally:
            db.close()

    def test_sync_run_checkpoint_roundtrip(self):
        db = self.Session()
        try:
            run = create_sync_run(db, job_type="activities_sync", job_id="j1")
            mark_sync_run_started(db, run.id)
            update_sync_run_checkpoint(
                db,
                run.id,
                {
                    "last_activity_id": "42",
                    "last_start_date": "2024-06-01",
                    "processed": 100,
                },
                inserted=80,
                updated=20,
                skipped=0,
            )
            db.refresh(run)
            self.assertEqual(run.checkpoint["last_activity_id"], "42")
            self.assertEqual(run.inserted, 80)
            incomplete = get_latest_incomplete_sync_run(db, job_type="activities_sync")
            self.assertIsNotNone(incomplete)
            self.assertEqual(incomplete.id, run.id)
        finally:
            db.close()

    def test_checkpoint_column_exists_after_migration(self):
        db = self.Session()
        try:
            run = SyncRun(
                job_type="test",
                status="processing",
                started_at=datetime.now(timezone.utc),
                checkpoint={"ok": True},
            )
            db.add(run)
            db.commit()
            db.refresh(run)
            self.assertEqual(run.checkpoint, {"ok": True})
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
