#!/usr/bin/env python3
"""
Idempotent SQLite-migrasjon: legger til avanserte EF- og decoupling-felt på activities.
"""

import sqlite3
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent
db_path = project_root / "data" / "treningsanalyse.db"

NEW_COLUMNS = [
    ("avg_efficiency_factor", "REAL"),
    ("median_efficiency_factor", "REAL"),
    ("steady_state_efficiency_factor", "REAL"),
    ("efficiency_data_quality", "REAL"),
    ("decoupling_suitability_flag", "TEXT"),
    ("decoupling_reason_if_unsuitable", "TEXT"),
    ("decoupling_data_quality_score", "REAL"),
    ("fatigue_resistance_score", "REAL"),
    ("pace_drop_pct", "REAL"),
    ("hr_drift_pct", "REAL"),
    ("cadence_drop_pct", "REAL"),
    ("ef_drop_pct", "REAL"),
]


def migrate_add_advanced_running_metrics() -> bool:
    if not db_path.exists():
        print(f"Database ikke funnet: {db_path}")
        return False

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='activities';")
        if not cursor.fetchone():
            print("Activities-tabellen finnes ikke")
            return False

        cursor.execute("PRAGMA table_info(activities);")
        existing_columns = {col[1] for col in cursor.fetchall()}

        added = 0
        for column_name, column_type in NEW_COLUMNS:
            if column_name in existing_columns:
                print(f"  Kolonne finnes allerede: {column_name}")
                continue
            cursor.execute(f"ALTER TABLE activities ADD COLUMN {column_name} {column_type};")
            print(f"  Lagt til kolonne: {column_name}")
            added += 1

        conn.commit()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS analytics_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_key VARCHAR(100) NOT NULL UNIQUE,
                payload JSON,
                calculated_at DATETIME,
                data_quality_score REAL,
                model_quality VARCHAR(50)
            );
            """
        )
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_analytics_snapshots_metric_key "
            "ON analytics_snapshots(metric_key);"
        )
        conn.commit()

        cursor.execute("PRAGMA table_info(activities);")
        columns_after = {col[1] for col in cursor.fetchall()}
        missing = [name for name, _ in NEW_COLUMNS if name not in columns_after]
        if missing:
            print(f"Feil: mangler kolonner etter migrering: {missing}")
            return False

        print(f"Ferdig. {added} nye kolonner lagt til.")
        return True
    except Exception as exc:
        print(f"Feil ved migrering: {exc}")
        return False
    finally:
        if "conn" in locals():
            conn.close()


if __name__ == "__main__":
    print("Migrerer database for avanserte løpemetrics...")
    success = migrate_add_advanced_running_metrics()
    if not success:
        sys.exit(1)
    print("Database-migrering fullført.")
