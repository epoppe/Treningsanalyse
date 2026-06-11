#!/usr/bin/env python3
"""
Regenerer sammendrag (daily/weekly/monthly/yearly) for å fylle best_* og yearly-trender.

Eksempler:
  python scripts/backfill_summary_fields.py --dry-run
  python scripts/backfill_summary_fields.py --json
  python scripts/backfill_summary_fields.py --yearly-only
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.database.session import SessionLocal  # noqa: E402
from app.services.summary_metric_backfill import (  # noqa: E402
    audit_summary_best_fields,
    run_summary_metric_backfill,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill sammendragsfelter fra lokale aktiviteter")
    parser.add_argument("--dry-run", action="store_true", help="Rull tilbake etter analyse")
    parser.add_argument("--json", action="store_true", help="Skriv JSON-sammendrag")
    parser.add_argument("--daily-only", action="store_true")
    parser.add_argument("--weekly-only", action="store_true")
    parser.add_argument("--monthly-only", action="store_true")
    parser.add_argument("--yearly-only", action="store_true")
    args = parser.parse_args()

    daily = weekly = monthly = yearly = True
    if args.daily_only:
        weekly = monthly = yearly = False
    elif args.weekly_only:
        daily = monthly = yearly = False
    elif args.monthly_only:
        daily = weekly = yearly = False
    elif args.yearly_only:
        daily = weekly = monthly = False

    db = SessionLocal()
    try:
        before = audit_summary_best_fields(db)
        summary = run_summary_metric_backfill(
            db,
            daily=daily,
            weekly=weekly,
            monthly=monthly,
            yearly=yearly,
            dry_run=args.dry_run,
        )
        after = audit_summary_best_fields(db)
        payload = {
            "dry_run": args.dry_run,
            "daily_count": summary.daily_count,
            "weekly_count": summary.weekly_count,
            "monthly_count": summary.monthly_count,
            "yearly_count": summary.yearly_count,
            "field_counts": summary.field_counts,
            "before": before,
            "after": after,
        }
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print("=== Summary backfill ===")
            print(f"Dry run: {args.dry_run}")
            print(f"Daglig: {summary.daily_count}, ukentlig: {summary.weekly_count}")
            print(f"Månedlig: {summary.monthly_count}, årlig: {summary.yearly_count}")
            if summary.field_counts:
                print("\nFelter fylt (delta):")
                for field_name, count in sorted(summary.field_counts.items()):
                    print(f"  {field_name}: +{count}")
            print("\nEtter backfill:")
            for field_name, stats in sorted(after.items()):
                print(f"  {field_name}: {stats['filled']}/{stats['total']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
