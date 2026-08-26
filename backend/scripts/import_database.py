"""CLI: import an existing Treningsanalyse SQLite DB into the configured data dir."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def main() -> int:
    parser = argparse.ArgumentParser(description="Importer eksisterende Treningsanalyse-database")
    parser.add_argument("source", help="Sti til kilde .db-fil")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Tillat overskriving av eksisterende mål-DB (tar backup først)",
    )
    parser.add_argument("--skip-migrate", action="store_true")
    args = parser.parse_args()

    from app.database.import_database import import_sqlite_database

    try:
        result = import_sqlite_database(
            args.source,
            allow_overwrite=args.overwrite,
            run_alembic=not args.skip_migrate,
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
