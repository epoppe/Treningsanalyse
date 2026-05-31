#!/usr/bin/env python3
"""
Reparer aktivitetsfelter (puls, stride, GCT) og kjør ruteanalyse på nytt.

Eksempel:
  python scripts/backfill_activity_data_validation.py --limit 500
  python scripts/backfill_activity_data_validation.py --routes-only --limit 200
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.config import settings  # noqa: E402
from app.database.session import SessionLocal  # noqa: E402
from app.database.models.activity import Activity  # noqa: E402
from app.storage import DataStorage  # noqa: E402
from app.services.activity_data_validation import validate_and_repair_activity  # noqa: E402
from app.services.route_analysis_service import RouteAnalysisService  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill aktivitetsvalidering og ruteanalyse")
    parser.add_argument("--limit", type=int, default=None, help="Maks antall aktiviteter")
    parser.add_argument(
        "--routes-only",
        action="store_true",
        help="Kun ruteanalyse (hopp over feltvalidering)",
    )
    parser.add_argument(
        "--validation-only",
        action="store_true",
        help="Kun feltvalidering (hopp over ruteanalyse)",
    )
    parser.add_argument(
        "--activity-id",
        type=str,
        default=None,
        help="Kun én aktivitet",
    )
    args = parser.parse_args()

    storage = DataStorage(settings.DATA_DIR)
    db = SessionLocal()
    route_service = RouteAnalysisService(storage)

    try:
        if args.activity_id:
            activities = [db.query(Activity).filter_by(activity_id=str(args.activity_id)).first()]
            activities = [a for a in activities if a]
        else:
            query = db.query(Activity).order_by(Activity.start_time.desc())
            if args.limit:
                query = query.limit(args.limit)
            activities = query.all()

        validation_summary = {"checked": 0, "changed": 0, "fixes": 0}
        route_summary = {"ok": 0, "skipped": 0, "error": 0}

        for activity in activities:
            if not args.routes_only:
                validation_summary["checked"] += 1
                result = validate_and_repair_activity(activity, storage=storage)
                if result.changed:
                    validation_summary["changed"] += 1
                    validation_summary["fixes"] += len(result.fixes)
            if not args.validation_only:
                route_result = route_service.analyze_activity(activity.activity_id, db)
                status = route_result.get("status")
                if status == "ok":
                    route_summary["ok"] += 1
                elif status == "skipped":
                    route_summary["skipped"] += 1
                else:
                    route_summary["error"] += 1

        db.commit()
        print("Validering:", validation_summary)
        print("Ruteanalyse:", route_summary)
    finally:
        db.close()


if __name__ == "__main__":
    main()
