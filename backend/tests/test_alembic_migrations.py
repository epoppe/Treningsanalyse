"""Tester for Alembic-migrasjoner og schema-versjonering."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.migrations import (
    get_head_revision,
    get_schema_version,
    run_migrations,
)
from app.database.models import Activity, ActivityType, Base


class AlembicMigrationTests(unittest.TestCase):
    def _make_engine(self, url: str):
        return create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

    def test_fresh_database_upgrade_head(self):
        """Ny database kan opprettes med alembic upgrade head."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "fresh.db"
            url = f"sqlite:///{db_path}"
            engine = self._make_engine(url)

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

    def test_legacy_database_stamp_preserves_data(self):
        """Eksisterende create_all-DB migreres uten datatap."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy.db"
            url = f"sqlite:///{db_path}"
            engine = self._make_engine(url)

            Base.metadata.create_all(bind=engine)
            Session = sessionmaker(bind=engine)
            db = Session()
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

    def test_upgrade_is_idempotent(self):
        """Gjentatt upgrade head er trygt."""
        url = "sqlite:///:memory:"
        engine = self._make_engine(url)
        first = run_migrations(engine, url)
        second = run_migrations(engine, url)
        self.assertEqual(first, second)

    def test_memory_database_shares_connection(self):
        """sqlite:///:memory: fungerer med StaticPool via delt connection."""
        url = "sqlite:///:memory:"
        engine = self._make_engine(url)
        revision = run_migrations(engine, url)
        tables = set(inspect(engine).get_table_names())
        self.assertIn("activities", tables)
        self.assertIn("alembic_version", tables)
        schema = get_schema_version(engine)
        self.assertEqual(schema["schema_version"], revision)
        self.assertTrue(schema["schema_at_head"])


if __name__ == "__main__":
    unittest.main()
