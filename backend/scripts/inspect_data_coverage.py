#!/usr/bin/env python3
"""
Kartlegg datadekning og foreslå backfill-prioritering uten å starte synk.

Eksempler:
  python scripts/inspect_data_coverage.py
  python scripts/inspect_data_coverage.py --json
  python scripts/inspect_data_coverage.py --recommendations-only
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.config import settings  # noqa: E402
from app.database.session import SessionLocal  # noqa: E402
from app.services.data_coverage_service import DataCoverageService  # noqa: E402
from app.storage import DataStorage  # noqa: E402


def _print_human(report) -> None:
    data = report.to_dict()
    activities = data["activities"]
    print("=== Datadekning (Treningsanalyse) ===")
    print(
        f"Aktiviteter: {activities['count']} "
        f"({activities['first_date']} → {activities['last_date']})"
    )

    print("\n--- Helsedata ---")
    for ds in data["datasets"]:
        span = ""
        if ds["first_date"] and ds["last_date"]:
            span = f"{ds['first_date']} → {ds['last_date']}"
        fill = ""
        if ds["expected_days"] is not None and ds["filled_days"] is not None:
            fill = f", fyllgrad {ds['filled_days']}/{ds['expected_days']}"
        missing = f", markert manglende {ds['missing_marked']}" if ds["missing_marked"] else ""
        sync = f", sync_state={ds['sync_state_date']}" if ds["sync_state_date"] else ""
        print(f"  {ds['label']}: {ds['row_count']} rader ({span}{fill}{missing}{sync})")
        if ds["notes"]:
            print(f"    {ds['notes']}")

    print("\n--- Aktivitetsfelter (utvalg) ---")
    for group, stats in data["activity_fields"].items():
        parts = []
        for field, info in stats["fields"].items():
            if info["count"]:
                parts.append(f"{field}={info['count']} ({info['pct']}%)")
        if parts:
            print(f"  {group}: {', '.join(parts)}")

    fit = data["fit"]
    print("\n--- FIT / detaljdata ---")
    print(
        f"  FIT-parquet: {fit['activities_with_fit']}/{fit['activities_total']} "
        f"({fit['fit_pct']}%)"
    )
    print(f"  FIT uten avledede metrikker: {fit['fit_missing_all_derived_metrics']}")
    if fit.get("fit_missing_derived_running") is not None:
        print(f"  daværende løp/tredemølle uten avledede: {fit['fit_missing_derived_running']}")
    print(f"  FIT uten EPOC: {fit['fit_missing_epoc']}")

    print("\n--- Anbefalt backfill-prioritet ---")
    for rec in data["recommendations"]:
        print(f"  P{rec['priority']} [{rec['risk']}] {rec['title']}")
        print(f"      Årsak: {rec['cause']} | MCP-verdi: {rec['value_for_mcp']}")
        print(f"      Scope: {rec['estimated_scope']}")
        print(f"      Handling: {rec['action']}")
        if rec["notes"]:
            print(f"      Merknad: {rec['notes']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Kartlegg datadekning og backfill-prioritet")
    parser.add_argument("--json", action="store_true", help="Skriv JSON i stedet for lesbar tekst")
    parser.add_argument("--recommendations-only", action="store_true", help="Kun anbefalinger")
    args = parser.parse_args()

    storage = DataStorage(settings.DATA_DIR)
    db = SessionLocal()
    try:
        report = DataCoverageService(db, storage).build_report()
        if args.json:
            payload = report.to_dict()
            if args.recommendations_only:
                payload = {"recommendations": payload["recommendations"]}
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            if args.recommendations_only:
                for rec in report.recommendations:
                    print(f"P{rec.priority} {rec.title} — {rec.action}")
            else:
                _print_human(report)
    finally:
        db.close()


if __name__ == "__main__":
    main()
