"""Tester for SyncRun og sync_lock."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.migrations import run_migrations
from app.database.models import SyncLock, SyncRun
from app.services.sync_job_store import (
    acquire_job_slot,
    mark_job_processing,
    reset_sync_jobs_store_for_tests,
)
from app.services.sync_lock_service import (
    GLOBAL_SYNC_LOCK,
    get_lock,
    is_locked,
    release_lock,
    try_acquire_lock,
)
from app.services.sync_run_service import extract_stats_from_result


class SyncLockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp.name) / "lock.db"
        self.url = f"sqlite:///{db_path}"
        self.engine = create_engine(
            self.url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        run_migrations(self.engine, self.url)
        self.Session = sessionmaker(bind=self.engine)
        # Pek app SessionLocal mot test-DB via monkeypatch av engine i session module
        import app.database.session as session_mod
        import app.services.sync_job_store as job_store_mod

        self._orig_engine = session_mod.engine
        self._orig_session = session_mod.SessionLocal
        session_mod.engine = self.engine
        session_mod.SessionLocal = self.Session
        job_store_mod.SessionLocal = self.Session
        reset_sync_jobs_store_for_tests()

    def tearDown(self):
        import app.database.session as session_mod
        import app.services.sync_job_store as job_store_mod

        reset_sync_jobs_store_for_tests()
        session_mod.engine = self._orig_engine
        session_mod.SessionLocal = self._orig_session
        job_store_mod.SessionLocal = self._orig_session
        self.engine.dispose()
        self.tmp.cleanup()

    def test_lock_exclusive(self):
        db = self.Session()
        try:
            self.assertTrue(try_acquire_lock(db, GLOBAL_SYNC_LOCK, "owner-a"))
            self.assertTrue(is_locked(db))
            self.assertFalse(try_acquire_lock(db, GLOBAL_SYNC_LOCK, "owner-b"))
            self.assertTrue(release_lock(db, GLOBAL_SYNC_LOCK, "owner-a"))
            self.assertTrue(try_acquire_lock(db, GLOBAL_SYNC_LOCK, "owner-b"))
        finally:
            db.close()

    def test_expired_lock_can_be_taken_over(self):
        db = self.Session()
        try:
            self.assertTrue(try_acquire_lock(db, GLOBAL_SYNC_LOCK, "owner-a", ttl_seconds=1))
            row = get_lock(db, GLOBAL_SYNC_LOCK)
            row.expires = datetime.now(timezone.utc) - timedelta(seconds=5)
            db.commit()
            self.assertTrue(try_acquire_lock(db, GLOBAL_SYNC_LOCK, "owner-b"))
            self.assertEqual(get_lock(db, GLOBAL_SYNC_LOCK).owner, "owner-b")
        finally:
            db.close()

    def test_cleanup_stale_sync_lock_releases_orphan(self):
        from app.services.sync_lock_service import cleanup_stale_sync_lock

        db = self.Session()
        try:
            self.assertTrue(try_acquire_lock(db, GLOBAL_SYNC_LOCK, "orphan-job-id"))
            self.assertTrue(cleanup_stale_sync_lock(db, GLOBAL_SYNC_LOCK))
            self.assertFalse(is_locked(db))
        finally:
            db.close()

    def test_acquire_job_slot_holds_global_lock(self):
        job_id, job, reused = acquire_job_slot("activities_sync", "test")
        self.assertFalse(reused)
        db = self.Session()
        try:
            self.assertTrue(is_locked(db))
            self.assertEqual(get_lock(db).owner, job_id)
        finally:
            db.close()

        job_id2, job2, reused2 = acquire_job_slot("health_sync", "test2")
        self.assertTrue(reused2)
        self.assertEqual(job_id2, job_id)

        # Fullfør jobb → lås frigis
        job.update({"status": "completed", "result": {"added_count": 3}, "end_time": datetime.now(timezone.utc)})
        db = self.Session()
        try:
            self.assertFalse(is_locked(db))
        finally:
            db.close()


class SyncRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp.name) / "run.db"
        self.url = f"sqlite:///{db_path}"
        self.engine = create_engine(
            self.url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        run_migrations(self.engine, self.url)
        self.Session = sessionmaker(bind=self.engine)
        import app.database.session as session_mod
        import app.services.sync_job_store as job_store_mod
        import app.services.sync_run_service as run_svc

        self._orig_engine = session_mod.engine
        self._orig_session = session_mod.SessionLocal
        session_mod.engine = self.engine
        session_mod.SessionLocal = self.Session
        job_store_mod.SessionLocal = self.Session
        run_svc.SessionLocal = self.Session
        reset_sync_jobs_store_for_tests()

    def tearDown(self):
        import app.database.session as session_mod
        import app.services.sync_job_store as job_store_mod
        import app.services.sync_run_service as run_svc

        reset_sync_jobs_store_for_tests()
        session_mod.engine = self._orig_engine
        session_mod.SessionLocal = self._orig_session
        job_store_mod.SessionLocal = self._orig_session
        run_svc.SessionLocal = self._orig_session
        self.engine.dispose()
        self.tmp.cleanup()

    def test_sync_run_created_and_completed_with_stats(self):
        job_id, job, _ = acquire_job_slot("full_sync", "queued")
        mark_job_processing(job_id, "processing")
        self.assertIsNotNone(job.get("sync_run_id"))

        db = self.Session()
        try:
            run = db.query(SyncRun).filter_by(id=job["sync_run_id"]).one()
            self.assertEqual(run.status, "processing")
            self.assertEqual(run.job_type, "full_sync")
            self.assertIsNotNone(run.started_at)
            self.assertIsNotNone(run.code_version)
        finally:
            db.close()

        job.update(
            {
                "status": "completed",
                "result": {"added_count": 5, "updated_count": 2, "skipped_count": 1},
                "end_time": datetime.now(timezone.utc),
            }
        )

        db = self.Session()
        try:
            run = db.query(SyncRun).filter_by(id=job["sync_run_id"]).one()
            self.assertEqual(run.status, "completed")
            self.assertEqual(run.inserted, 5)
            self.assertEqual(run.updated, 2)
            self.assertEqual(run.skipped, 1)
            self.assertIsNotNone(run.completed_at)
            self.assertEqual(db.query(SyncLock).count(), 0)
        finally:
            db.close()

    def test_extract_stats_from_result(self):
        stats = extract_stats_from_result(
            {"added_count": 10, "updated": 3, "activities": {"skipped_count": 2}}
        )
        self.assertEqual(stats["inserted"], 10)
        self.assertEqual(stats["updated"], 3)
        self.assertEqual(stats["skipped"], 2)

    def test_failed_run_stores_error(self):
        job_id, job, _ = acquire_job_slot("fit_download", "queued")
        mark_job_processing(job_id)
        job.update({"status": "failed", "error": "boom", "end_time": datetime.now(timezone.utc)})
        db = self.Session()
        try:
            run = db.query(SyncRun).filter_by(id=job["sync_run_id"]).one()
            self.assertEqual(run.status, "failed")
            self.assertEqual(run.last_error, "boom")
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
