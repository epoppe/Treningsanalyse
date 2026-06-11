#!/usr/bin/env python3
"""
Kontrollert backfill av manglende aktivitetsfelter fra lokale kilder.

Prioritet:
  average_pace, max_running_cadence, moving/elapsed_duration, total_steps, min/max_elevation

Kilder (i rekkefølge):
  1. Garmin activities.json / activities_*.json (hvis finnes)
  2. FIT/parquet (cadence, høyde, varighet, steg)
  3. Avledning fra distance/duration eller average_speed

Ingen Garmin-nedlasting.

Eksempler:
  python scripts/backfill_activity_fields.py --dry-run
  python scripts/backfill_activity_fields.py --limit 500
  python scripts/backfill_activity_fields.py --activity-id 22416887746
  python scripts/backfill_activity_fields.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.config import settings  # noqa: E402
from app.database.models.activity import Activity  # noqa: E402
from app.database.session import SessionLocal  # noqa: E402
from app.services.activity_metric_backfill import apply_activity_field_backfill  # noqa: E402
from app.storage import DataStorage  # noqa: E402

TARGET_FIELDS = [
    "average_pace",
    "max_running_cadence",
    "moving_duration",
    "elapsed_duration",
    "total_steps",
    "min_elevation",
    "max_elevation",
]


def _field_counts(db, activity_ids: Optional[List[str]] = None) -> Dict[str, int]:
    query = db.query(Activity)
    if activity_ids:
        query = query.filter(Activity.activity_id.in_(activity_ids))
    rows = query.all()
    counts = {field: 0 for field in TARGET_FIELDS}
    for activity in rows:
        for field in TARGET_FIELDS:
            if getattr(activity, field, None) is not None:
                counts[field] += 1
    return counts


def _build_garmin_list_index(storage: DataStorage) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for item in storage.get_activities():
        aid = item.get("activityId") or item.get("id")
        if aid is not None:
            index[str(aid)] = item
    return index


def _candidate_query(db, *, activity_id: Optional[str], limit: Optional[int]):
    if activity_id:
        return [db.query(Activity).filter_by(activity_id=str(activity_id)).first()]
    filters = [
        Activity.average_pace.is_(None),
        Activity.max_running_cadence.is_(None),
        Activity.moving_duration.is_(None),
        Activity.elapsed_duration.is_(None),
        Activity.total_steps.is_(None),
        Activity.min_elevation.is_(None),
        Activity.max_elevation.is_(None),
    ]
    from sqlalchemy import or_

    query = (
        db.query(Activity)
        .filter(or_(*filters))
        .order_by(Activity.start_time.desc())
    )
    if limit is not None:
        query = query.limit(limit)
    return query.all()


def run_backfill(
    *,
    limit: Optional[int],
    activity_id: Optional[str],
    dry_run: bool,
    progress_every: int,
) -> Dict[str, Any]:
    storage = DataStorage(settings.DATA_DIR)
    db = SessionLocal()
    garmin_index = _build_garmin_list_index(storage)

    summary: Dict[str, Any] = {
        "candidates": 0,
        "processed": 0,
        "changed": 0,
        "field_updates": {field: 0 for field in TARGET_FIELDS},
        "examples": [],
    }

    try:
        candidates = _candidate_query(db, activity_id=activity_id, limit=limit)
        candidates = [activity for activity in candidates if activity is not None]
        summary["candidates"] = len(candidates)
        candidate_ids = [str(activity.activity_id) for activity in candidates]
        summary["before"] = _field_counts(db, candidate_ids if candidate_ids else None)

        if dry_run:
            for activity in candidates:
                before = {field: getattr(activity, field) for field in TARGET_FIELDS}
                result = apply_activity_field_backfill(
                    activity,
                    storage=storage,
                    garmin_list=garmin_index.get(str(activity.activity_id)),
                )
                summary["processed"] += 1
                if result.changed:
                    summary["changed"] += 1
                    for field in TARGET_FIELDS:
                        if before[field] is None and getattr(activity, field) is not None:
                            summary["field_updates"][field] += 1
                    if len(summary["examples"]) < 8:
                        summary["examples"].append(
                            {
                                "activity_id": activity.activity_id,
                                "fixes": result.fixes,
                                "filled": {
                                    field: getattr(activity, field)
                                    for field in TARGET_FIELDS
                                    if before[field] is None and getattr(activity, field) is not None
                                },
                            }
                        )
                for field in TARGET_FIELDS:
                    setattr(activity, field, before[field])
            summary["after"] = summary["before"]
            return summary

        for index, activity in enumerate(candidates, start=1):
            before = {field: getattr(activity, field) for field in TARGET_FIELDS}
            result = apply_activity_field_backfill(
                activity,
                storage=storage,
                garmin_list=garmin_index.get(str(activity.activity_id)),
            )
            summary["processed"] += 1
            if result.changed:
                summary["changed"] += 1
                for field in TARGET_FIELDS:
                    if before[field] is None and getattr(activity, field) is not None:
                        summary["field_updates"][field] += 1
                if len(summary["examples"]) < 8:
                    summary["examples"].append(
                        {
                            "activity_id": activity.activity_id,
                            "fixes": result.fixes,
                            "filled": {
                                field: getattr(activity, field)
                                for field in TARGET_FIELDS
                                if before[field] is None and getattr(activity, field) is not None
                            },
                        }
                    )

            if progress_every > 0 and (
                index == 1 or index == len(candidates) or index % progress_every == 0
            ):
                print(
                    f"  [{index}/{len(candidates)}] endret={summary['changed']} "
                    f"pace+={summary['field_updates']['average_pace']}",
                    flush=True,
                )

        db.commit()
        db.expire_all()
        summary["after"] = _field_counts(db, candidate_ids if candidate_ids else None)
        return summary
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill manglende aktivitetsfelter fra lokale kilder")
    parser.add_argument("--limit", type=int, default=None, help="Maks kandidater")
    parser.add_argument("--activity-id", type=str, default=None, help="Kun én aktivitet")
    parser.add_argument("--dry-run", action="store_true", help="Simuler uten å lagre")
    parser.add_argument("--json", action="store_true", help="Skriv JSON-sammendrag")
    parser.add_argument("--progress-every", type=int, default=100, help="Logg fremdrift hvert N-te (0=av)")
    args = parser.parse_args()

    summary = run_backfill(
        limit=args.limit,
        activity_id=args.activity_id,
        dry_run=args.dry_run,
        progress_every=args.progress_every,
    )

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return

    mode = "DRY-RUN" if args.dry_run else "BACKFILL"
    print(f"=== {mode}: aktivitetsfelter ===")
    print(f"Kandidater: {summary['candidates']}")
    print(f"Prosessert: {summary['processed']}")
    print(f"Endret: {summary['changed']}")
    print("\nFelt oppdatert (blant kandidater):")
    for field in TARGET_FIELDS:
        print(f"  {field}: +{summary['field_updates'][field]}")
    if summary.get("before") and summary.get("after"):
        print("\nFør/etter (blant kandidater):")
        for field in TARGET_FIELDS:
            print(f"  {field}: {summary['before'][field]} → {summary['after'][field]}")
    if summary.get("examples"):
        print("\nEksempler:")
        for item in summary["examples"]:
            print(f"  {item['activity_id']}: {item['filled']}")


if __name__ == "__main__":
    main()
