#!/usr/bin/env python3
"""Idempotent SQLite migration for richer Garmin performance metrics."""

from __future__ import annotations

import logging
from pathlib import Path
import sys

from sqlalchemy import inspect, text

sys.path.append(str(Path(__file__).parent))

from app.database.session import engine

logger = logging.getLogger(__name__)


ACTIVITY_COLUMNS = {
    "average_moving_speed": "FLOAT",
    "avg_grade_adjusted_speed": "FLOAT",
    "ground_contact_time": "FLOAT",
    "stride_length": "FLOAT",
    "vertical_oscillation": "FLOAT",
    "vertical_ratio": "FLOAT",
    "training_effect_label": "VARCHAR(100)",
    "aerobic_training_effect_message": "VARCHAR(255)",
    "anaerobic_training_effect_message": "VARCHAR(255)",
    "vo2_max_precise": "FLOAT",
    "begin_potential_stamina": "FLOAT",
    "end_potential_stamina": "FLOAT",
    "min_available_stamina": "FLOAT",
    "activity_body_battery_delta": "FLOAT",
}


def _add_column_if_missing(conn, table_name: str, column_name: str, column_type: str) -> None:
    inspector = inspect(conn)
    existing = {col["name"] for col in inspector.get_columns(table_name)}
    if column_name not in existing:
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))


def migrate_add_garmin_performance_metrics() -> bool:
    try:
        with engine.begin() as conn:
            for column_name, column_type in ACTIVITY_COLUMNS.items():
                _add_column_if_missing(conn, "activities", column_name, column_type)

            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS garmin_performance_metrics (
                        date DATETIME NOT NULL PRIMARY KEY,
                        vo2_max FLOAT,
                        vo2_max_precise FLOAT,
                        fitness_age FLOAT,
                        max_met_category INTEGER,
                        altitude_acclimation FLOAT,
                        previous_altitude_acclimation FLOAT,
                        heat_acclimation_percentage FLOAT,
                        previous_heat_acclimation_percentage FLOAT,
                        current_altitude FLOAT,
                        heat_trend VARCHAR(100),
                        altitude_trend VARCHAR(100),
                        monthly_load_aerobic_low FLOAT,
                        monthly_load_aerobic_high FLOAT,
                        monthly_load_anaerobic FLOAT,
                        monthly_load_aerobic_low_target_min FLOAT,
                        monthly_load_aerobic_low_target_max FLOAT,
                        monthly_load_aerobic_high_target_min FLOAT,
                        monthly_load_aerobic_high_target_max FLOAT,
                        monthly_load_anaerobic_target_min FLOAT,
                        monthly_load_anaerobic_target_max FLOAT,
                        training_balance_feedback_phrase VARCHAR(100),
                        training_status INTEGER,
                        training_status_feedback_phrase VARCHAR(255),
                        sport VARCHAR(100),
                        sub_sport VARCHAR(100),
                        fitness_trend INTEGER,
                        fitness_trend_sport VARCHAR(100),
                        acwr_percent FLOAT,
                        acwr_status VARCHAR(100),
                        acwr_status_feedback VARCHAR(255),
                        daily_training_load_acute FLOAT,
                        daily_training_load_chronic FLOAT,
                        daily_acute_chronic_workload_ratio FLOAT,
                        load_tunnel_min FLOAT,
                        load_tunnel_max FLOAT,
                        endurance_score FLOAT,
                        endurance_classification INTEGER,
                        hill_score FLOAT,
                        hill_endurance_score FLOAT,
                        hill_strength_score FLOAT,
                        raw_maxmet JSON,
                        raw_training_load_balance JSON,
                        raw_training_status JSON,
                        raw_endurance_score JSON,
                        raw_hill_score JSON,
                        calculated_at DATETIME
                    )
                    """
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_garmin_performance_metrics_date "
                    "ON garmin_performance_metrics (date)"
                )
            )
        return True
    except Exception as exc:
        logger.error("Garmin performance metrics-migrasjon feilet: %s", exc)
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ok = migrate_add_garmin_performance_metrics()
    raise SystemExit(0 if ok else 1)
