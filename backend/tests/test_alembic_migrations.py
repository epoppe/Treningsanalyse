"""Tester for Alembic-migrasjoner og schema-versjonering."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.orm import sessionmaker

from app.database.migrations import (
    get_head_revision,
    get_schema_version,
    run_migrations,
)
from app.database.models import Activity, ActivityType, Base
from tests.sqlite_test_utils import (
    dispose_engine,
    file_sqlite_url,
    make_file_engine,
    make_memory_engine,
)


class AlembicMigrationTests(unittest.TestCase):
    def test_fresh_database_upgrade_head(self):
        """Ny database kan opprettes med alembic upgrade head."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "fresh.db"
            url = file_sqlite_url(db_path)
            engine = make_file_engine(url)
            try:
                revision = run_migrations(engine, url)
                head = get_head_revision(url)

                self.assertEqual(revision, head)
                self.assertIsNotNone(revision)

                tables = set(inspect(engine).get_table_names())
                self.assertIn("activities", tables)
                self.assertIn("alembic_version", tables)
                self.assertIn("garmin_performance_metrics", tables)
                self.assertIn("activity_route_fingerprints", tables)
                self.assertIn("sync_jobs", tables)

                with engine.connect() as conn:
                    version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
                self.assertEqual(version, revision)

                schema = get_schema_version(engine)
                self.assertTrue(schema["schema_at_head"])
                self.assertEqual(schema["schema_version"], revision)
            finally:
                dispose_engine(engine)

    def test_legacy_database_stamp_preserves_data(self):
        """Eksisterende create_all-DB migreres uten datatap."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy.db"
            url = file_sqlite_url(db_path)
            engine = make_file_engine(url)
            try:
                Base.metadata.create_all(bind=engine)
                Session = sessionmaker(bind=engine)
                db = Session()
                try:
                    db.add(ActivityType(type_key="running", type_name="Løping"))
                    db.add(
                        Activity(
                            activity_id="legacy-1",
                            activity_name="Bevart økt",
                            distance=10000.0,
                            duration=3600.0,
                        )
                    )
                    db.commit()
                finally:
                    db.close()

                revision = run_migrations(engine, url)
                self.assertEqual(revision, get_head_revision(url))

                db = Session()
                try:
                    self.assertEqual(db.query(Activity).count(), 1)
                    activity = db.query(Activity).one()
                    self.assertEqual(activity.activity_id, "legacy-1")
                    self.assertEqual(activity.activity_name, "Bevart økt")
                    self.assertEqual(activity.distance, 10000.0)
                finally:
                    db.close()
            finally:
                dispose_engine(engine)

    def test_upgrade_is_idempotent(self):
        """Gjentatt upgrade head er trygt."""
        url = "sqlite:///:memory:"
        engine = make_memory_engine(url)
        try:
            first = run_migrations(engine, url)
            second = run_migrations(engine, url)
            self.assertEqual(first, second)
        finally:
            dispose_engine(engine)

    def test_memory_database_shares_connection(self):
        """sqlite:///:memory: fungerer med StaticPool via delt connection."""
        url = "sqlite:///:memory:"
        engine = make_memory_engine(url)
        try:
            revision = run_migrations(engine, url)
            tables = set(inspect(engine).get_table_names())
            self.assertIn("activities", tables)
            self.assertIn("alembic_version", tables)
            schema = get_schema_version(engine)
            self.assertEqual(schema["schema_version"], revision)
            self.assertTrue(schema["schema_at_head"])
        finally:
            dispose_engine(engine)

    def test_single_alembic_head(self):
        from app.database.migrations import assert_single_alembic_head, get_all_heads

        heads = get_all_heads()
        self.assertEqual(len(heads), 1)
        self.assertEqual(assert_single_alembic_head(), heads[0])

    def test_query_performance_indexes_exist(self):
        """Fase 4: FK-/query-indekser for laps, PR, sync og TE-backfill."""
        url = "sqlite:///:memory:"
        engine = make_memory_engine(url)
        try:
            run_migrations(engine, url)
            inspector = inspect(engine)

            lap_indexes = {idx["name"] for idx in inspector.get_indexes("activity_laps")}
            self.assertIn("ix_activity_laps_activity_id", lap_indexes)

            pr_indexes = {idx["name"] for idx in inspector.get_indexes("personal_records")}
            self.assertIn("ix_personal_records_activity_id", pr_indexes)

            run_indexes = {idx["name"] for idx in inspector.get_indexes("sync_runs")}
            self.assertIn("idx_sync_runs_status_job_type", run_indexes)

            job_indexes = {idx["name"] for idx in inspector.get_indexes("sync_jobs")}
            self.assertIn("idx_sync_jobs_status_job_type", job_indexes)

            activity_indexes = {idx["name"] for idx in inspector.get_indexes("activities")}
            self.assertIn("idx_activities_missing_training_effect", activity_indexes)

            tables = set(inspector.get_table_names())
            self.assertIn("recommendation_records", tables)
            self.assertIn("training_plans", tables)
            self.assertIn("training_plan_versions", tables)
            self.assertIn("athlete_feedback", tables)
            self.assertIn("training_availability", tables)
            self.assertIn("training_experiments", tables)
            self.assertIn("coaching_model_registry", tables)
            self.assertIn("shadow_recommendations", tables)
            self.assertIn("validation_runs", tables)
        finally:
            dispose_engine(engine)


if __name__ == "__main__":
    unittest.main()
