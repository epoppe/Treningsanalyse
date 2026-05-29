#!/usr/bin/env python3
"""Idempotent SQLite migration for GPS route analysis tables."""

from __future__ import annotations

import logging
from pathlib import Path
import sys

from sqlalchemy import text

sys.path.append(str(Path(__file__).parent))

from app.database.session import engine

logger = logging.getLogger(__name__)


def migrate_add_route_analysis() -> bool:
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS activity_route_fingerprints (
                        activity_id VARCHAR(255) NOT NULL PRIMARY KEY,
                        route_group_key VARCHAR(100),
                        route_hash VARCHAR(64),
                        point_count INTEGER,
                        gps_point_count INTEGER,
                        sampled_point_count INTEGER,
                        route_distance_m FLOAT,
                        start_latitude FLOAT,
                        start_longitude FLOAT,
                        end_latitude FLOAT,
                        end_longitude FLOAT,
                        centroid_latitude FLOAT,
                        centroid_longitude FLOAT,
                        bbox_min_latitude FLOAT,
                        bbox_min_longitude FLOAT,
                        bbox_max_latitude FLOAT,
                        bbox_max_longitude FLOAT,
                        quality_score FLOAT,
                        sampled_points JSON,
                        calculated_at DATETIME,
                        method_version VARCHAR(30),
                        FOREIGN KEY(activity_id) REFERENCES activities (activity_id)
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS activity_route_matches (
                        id INTEGER NOT NULL PRIMARY KEY,
                        activity_id VARCHAR(255) NOT NULL,
                        matched_activity_id VARCHAR(255) NOT NULL,
                        same_route BOOLEAN NOT NULL DEFAULT 0,
                        similarity_score FLOAT NOT NULL,
                        reverse_direction BOOLEAN NOT NULL DEFAULT 0,
                        mean_distance_m FLOAT,
                        p90_distance_m FLOAT,
                        start_distance_m FLOAT,
                        end_distance_m FLOAT,
                        distance_ratio FLOAT,
                        overlap_quality FLOAT,
                        calculated_at DATETIME,
                        method_version VARCHAR(30),
                        FOREIGN KEY(activity_id) REFERENCES activities (activity_id),
                        FOREIGN KEY(matched_activity_id) REFERENCES activities (activity_id),
                        CONSTRAINT uq_activity_route_match_pair UNIQUE (activity_id, matched_activity_id)
                    )
                    """
                )
            )
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_activity_route_fingerprints_route_group_key ON activity_route_fingerprints (route_group_key)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_activity_route_fingerprints_route_hash ON activity_route_fingerprints (route_hash)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_route_match_activity_score ON activity_route_matches (activity_id, similarity_score)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_route_match_same_route ON activity_route_matches (same_route, similarity_score)"))
        return True
    except Exception as exc:
        logger.error("Ruteanalyse-migrasjon feilet: %s", exc)
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ok = migrate_add_route_analysis()
    raise SystemExit(0 if ok else 1)

