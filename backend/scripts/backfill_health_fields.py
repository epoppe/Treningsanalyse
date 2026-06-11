#!/usr/bin/env python3
"""
Kontrollert backfill av helsedatafelter fra lokale kilder (ingen Garmin-nedlasting).

Prioritet:
  1. sleep.* sidefelter fra kolonner og detailed_sleep_data
  2. performance.* fra lagret raw_* JSON
  3. activity.vo2_max_precise fra daglig GarminPerformanceMetric
  4. activity.training_readiness_score fra lokal TrainingReadinessService
  5. body_battery.net_charge når charged/drained allerede finnes

Eksempler:
  python scripts/backfill_health_fields.py --dry-run
  python scripts/backfill_health_fields.py --json
  python scripts/backfill_health_fields.py --sleep-only
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.database.session import SessionLocal  # noqa: E402
from app.services.health_metric_backfill import run_health_metric_backfill  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill helsedatafelter fra lokale kilder")
    parser.add_argument("--dry-run", action="store_true", help="Rull tilbake etter analyse")
    parser.add_argument("--limit", type=int, default=None, help="Maks rader per datasett")
    parser.add_argument("--json", action="store_true", help="Skriv JSON-sammendrag")
    parser.add_argument("--sleep-only", action="store_true")
    parser.add_argument("--performance-only", action="store_true")
    parser.add_argument("--activities-only", action="store_true")
    parser.add_argument("--body-battery-only", action="store_true")
    parser.add_argument("--readiness-only", action="store_true")
    args = parser.parse_args()

    sleep = performance = activities = readiness = body_battery = True
    if args.sleep_only:
        performance = activities = readiness = body_battery = False
    elif args.performance_only:
        sleep = activities = readiness = body_battery = False
    elif args.activities_only:
        sleep = performance = readiness = body_battery = False
    elif args.readiness_only:
        sleep = performance = activities = body_battery = False
    elif args.body_battery_only:
        sleep = performance = activities = readiness = False

    db = SessionLocal()
    try:
        summary = run_health_metric_backfill(
            db,
            sleep=sleep,
            performance=performance,
            activities=activities,
            readiness=readiness,
            body_battery=body_battery,
            limit=args.limit,
            dry_run=args.dry_run,
        )
        payload = {
            "dry_run": args.dry_run,
            "sleep_rows_updated": summary.sleep_rows_updated,
            "performance_rows_updated": summary.performance_rows_updated,
            "activity_rows_updated": summary.activity_rows_updated,
            "readiness_days_updated": summary.readiness_days_updated,
            "readiness_days_skipped": summary.readiness_days_skipped,
            "body_battery_rows_updated": summary.body_battery_rows_updated,
            "field_counts": summary.field_counts,
            "examples": summary.examples,
        }
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print("=== Health backfill ===")
            print(f"Dry run: {args.dry_run}")
            print(f"Søvn-rader oppdatert: {summary.sleep_rows_updated}")
            print(f"Performance-rader oppdatert: {summary.performance_rows_updated}")
            print(f"Aktivitets-rader oppdatert: {summary.activity_rows_updated}")
            print(f"Readiness-dager oppdatert: {summary.readiness_days_updated}")
            print(f"Readiness-dager hoppet over (ikke robust): {summary.readiness_days_skipped}")
            print(f"Body Battery-rader oppdatert: {summary.body_battery_rows_updated}")
            if summary.field_counts:
                print("\nFelter fylt:")
                for field_name, count in sorted(summary.field_counts.items()):
                    print(f"  {field_name}: {count}")
            if summary.examples:
                print("\nEksempler:")
                for example in summary.examples[:5]:
                    print(f"  {example}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
