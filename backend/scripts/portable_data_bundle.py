#!/usr/bin/env python3
"""
Eksporter / importer portabel datapakke for Treningsanalyse (SQLite + parquet + MCP-snapshot).

Brukes for å flytte alle lokale trenings- og helsedata til et likt repo på en annen maskin.
Inkluderer IKKE Garmin-tokens (.env / backend/tokens) — synk mot Garmin må settes opp på ny maskin.

Eksempler:
  python scripts/portable_data_bundle.py export
  python scripts/portable_data_bundle.py export --output ../exports/min_bundle.zip
  python scripts/portable_data_bundle.py import --bundle ../exports/min_bundle.zip
  python scripts/portable_data_bundle.py import --bundle pakke.zip --dry-run
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.config import settings  # noqa: E402

BUNDLE_VERSION = 1
MANIFEST_NAME = "manifest.json"
README_NAME = "IMPORT_README.txt"

# Relative paths inside zip (POSIX-style)
DATA_PREFIX = "backend/data"
MCP_PREFIX = "mcp"
HEALTH_PREFIX = "health"

SKIP_DATA_SUFFIXES = {".db-wal", ".db-shm", ".tmp", ".lock"}
INCLUDE_DATA_SUFFIXES = {".parquet", ".json", ".db"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_table_counts(db_path: Path) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    if not db_path.exists():
        return counts
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        for table in tables:
            try:
                counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0])
            except sqlite3.Error:
                continue
    finally:
        conn.close()
    return counts


def _backup_sqlite(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dst = sqlite3.connect(destination)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()


def _iter_data_files(data_dir: Path) -> Iterable[Path]:
    if not data_dir.exists():
        return
    for path in sorted(data_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() in SKIP_DATA_SUFFIXES:
            continue
        if path.suffix.lower() not in INCLUDE_DATA_SUFFIXES:
            continue
        if path.name == "treningsanalyse.db":
            continue
        yield path


def _readme_text() -> str:
    return """Treningsanalyse — portabel datapakke
=====================================

Innhold:
  backend/data/treningsanalyse.db   Hoveddatabase (aktiviteter, søvn, stress, performance, …)
  backend/data/*.parquet            FIT-detaljer og parquet-baserte tidsserier
  mcp/MCP_FRESH_VALUES.*            Siste MCP-metrikk-snapshot (valgfritt)
  health/health.db                  Separat helsedatabase hvis eksportert (valgfritt)

IKKE inkludert: Garmin OAuth-tokens, .env, Redis-cache.

Import på ny maskin
-------------------
1. Klon/kopier Treningsanalyse-repoet og installer backend (.venv + pip install -r requirements.txt).
2. Fra backend-mappen:
     python scripts/portable_data_bundle.py import --bundle /sti/til/pakken.zip
3. Start backend (uvicorn) og verifiser i UI / MCP.
4. Sett opp Garmin-pålogging (.env + tokens) om du vil synke nye data.

Tips:
  - Stopp backend under import hvis den kjører.
  - Eksisterende data backup'es automatisk til backend/data/_backup_before_import_<timestamp>/.
"""


def _collect_stats(data_dir: Path, db_backup: Path) -> Dict[str, Any]:
    counts = _sqlite_table_counts(db_backup)
    return {
        "sqlite_tables": counts,
        "activities": counts.get("activities"),
        "activity_details_parquet_bytes": (
            (data_dir / "activity_details.parquet").stat().st_size
            if (data_dir / "activity_details.parquet").exists()
            else 0
        ),
    }


def export_bundle(
    output: Optional[Path] = None,
    *,
    include_mcp: bool = True,
    include_health_db: bool = True,
) -> Path:
    data_dir = Path(settings.DATA_DIR)
    if not data_dir.exists():
        raise FileNotFoundError(f"DATA_DIR finnes ikke: {data_dir}")

    main_db = data_dir / "treningsanalyse.db"
    if not main_db.exists():
        raise FileNotFoundError(f"Mangler hoveddatabase: {main_db}")

    if output is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_dir = BACKEND / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        output = export_dir / f"treningsanalyse_portable_{stamp}.zip"
    else:
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)

    manifest_files: List[Dict[str, Any]] = []

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        db_backup = tmp_path / "treningsanalyse.db"
        _backup_sqlite(main_db, db_backup)

        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            zf.writestr(README_NAME, _readme_text())

            arc_db = f"{DATA_PREFIX}/treningsanalyse.db"
            zf.write(db_backup, arc_db)
            manifest_files.append(
                {
                    "path": arc_db,
                    "size": db_backup.stat().st_size,
                    "sha256": _sha256_file(db_backup),
                }
            )

            for file_path in _iter_data_files(data_dir):
                arc = f"{DATA_PREFIX}/{file_path.relative_to(data_dir).as_posix()}"
                zf.write(file_path, arc)
                manifest_files.append(
                    {
                        "path": arc,
                        "size": file_path.stat().st_size,
                        "sha256": _sha256_file(file_path),
                    }
                )

            if include_mcp:
                for name in ("MCP_FRESH_VALUES.json", "MCP_FRESH_VALUES.csv"):
                    mcp_file = ROOT / name
                    if mcp_file.exists():
                        arc = f"{MCP_PREFIX}/{name}"
                        zf.write(mcp_file, arc)
                        manifest_files.append(
                            {
                                "path": arc,
                                "size": mcp_file.stat().st_size,
                                "sha256": _sha256_file(mcp_file),
                            }
                        )

            health_db = ROOT / "health.db"
            if include_health_db and health_db.exists():
                arc = f"{HEALTH_PREFIX}/health.db"
                zf.write(health_db, arc)
                manifest_files.append(
                    {
                        "path": arc,
                        "size": health_db.stat().st_size,
                        "sha256": _sha256_file(health_db),
                    }
                )

            manifest = {
                "bundle_version": BUNDLE_VERSION,
                "created_at": _utc_now(),
                "project": "Treningsanalyse",
                "data_dir": str(data_dir),
                "includes_secrets": False,
                "includes": {
                    "sqlite": True,
                    "parquet": True,
                    "mcp_snapshot": include_mcp,
                    "health_db": include_health_db and (ROOT / "health.db").exists(),
                },
                "stats": _collect_stats(data_dir, db_backup),
                "files": manifest_files,
            }
            zf.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2, ensure_ascii=False))

    return output


def _resolve_target(arc_path: str, data_dir: Path, root_dir: Path) -> Path:
    if arc_path.startswith(f"{DATA_PREFIX}/"):
        rel = arc_path[len(DATA_PREFIX) + 1 :]
        return data_dir / rel
    if arc_path.startswith(f"{MCP_PREFIX}/"):
        rel = arc_path[len(MCP_PREFIX) + 1 :]
        return root_dir / rel
    if arc_path.startswith(f"{HEALTH_PREFIX}/"):
        rel = arc_path[len(HEALTH_PREFIX) + 1 :]
        return root_dir / rel
    raise ValueError(f"Ukjent sti i pakke: {arc_path}")


def import_bundle(
    bundle: Path,
    *,
    data_dir: Optional[Path] = None,
    root_dir: Optional[Path] = None,
    dry_run: bool = False,
    skip_backup: bool = False,
) -> Dict[str, Any]:
    bundle = Path(bundle)
    if not bundle.exists():
        raise FileNotFoundError(f"Finner ikke pakke: {bundle}")

    data_dir = Path(data_dir or settings.DATA_DIR)
    root_dir = Path(root_dir or ROOT)
    data_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(bundle, "r") as zf:
        if MANIFEST_NAME not in zf.namelist():
            raise ValueError(f"Ugyldig pakke: mangler {MANIFEST_NAME}")
        manifest = json.loads(zf.read(MANIFEST_NAME).decode("utf-8"))
        if manifest.get("bundle_version") != BUNDLE_VERSION:
            raise ValueError(
                f"Ustøttet bundle_version={manifest.get('bundle_version')} "
                f"(forventet {BUNDLE_VERSION})"
            )

        planned: List[Dict[str, Any]] = []
        for entry in manifest.get("files", []):
            arc = entry["path"]
            if arc == MANIFEST_NAME or arc == README_NAME:
                continue
            target = _resolve_target(arc, data_dir, root_dir)
            planned.append({"arc": arc, "target": str(target), "size": entry.get("size")})

        result = {
            "dry_run": dry_run,
            "bundle": str(bundle),
            "manifest_created_at": manifest.get("created_at"),
            "files": planned,
            "stats": manifest.get("stats"),
        }

        if dry_run:
            return result

        backup_dir: Optional[Path] = None
        if not skip_backup:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = data_dir / f"_backup_before_import_{stamp}"
            backup_dir.mkdir(parents=True, exist_ok=True)
            for item in planned:
                target = Path(item["target"])
                if not str(target).startswith(str(data_dir)):
                    continue
                if target.exists():
                    rel = target.relative_to(data_dir)
                    shutil.copy2(target, backup_dir / rel)
            result["data_backup_dir"] = str(backup_dir)

        for item in planned:
            target = Path(item["target"])
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(item["arc"]) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)

        for entry in manifest.get("files", []):
            arc = entry["path"]
            if arc in {MANIFEST_NAME, README_NAME}:
                continue
            target = _resolve_target(arc, data_dir, root_dir)
            if target.exists() and entry.get("sha256"):
                actual = _sha256_file(target)
                if actual != entry["sha256"]:
                    raise RuntimeError(f"Checksum mismatch etter import: {arc}")

        result["imported_files"] = len(planned)
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Portabel eksport/import av Treningsanalyse-data")
    sub = parser.add_subparsers(dest="command", required=True)

    export_p = sub.add_parser("export", help="Lag zip-pakke for flytting til annen maskin")
    export_p.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Utdata-zip (standard: backend/exports/treningsanalyse_portable_<timestamp>.zip)",
    )
    export_p.add_argument("--no-mcp", action="store_true", help="Utelat MCP_FRESH_VALUES-filer")
    export_p.add_argument("--no-health-db", action="store_true", help="Utelat health.db i rot")

    import_p = sub.add_parser("import", help="Importer zip-pakke til dette prosjektet")
    import_p.add_argument("--bundle", type=Path, required=True, help="Sti til zip fra export")
    import_p.add_argument("--data-dir", type=Path, default=None, help="Overstyr backend/data")
    import_p.add_argument("--dry-run", action="store_true", help="Vis plan uten å skrive filer")
    import_p.add_argument("--skip-backup", action="store_true", help="Ikke backup eksisterende data/")

    args = parser.parse_args()

    if args.command == "export":
        out = export_bundle(
            args.output,
            include_mcp=not args.no_mcp,
            include_health_db=not args.no_health_db,
        )
        print(f"Eksportert: {out}")
        print(f"Størrelse: {out.stat().st_size / (1024 * 1024):.1f} MiB")
        print("Importer på ny maskin:")
        print(f"  python scripts/portable_data_bundle.py import --bundle {out.name}")
        return

    result = import_bundle(
        args.bundle,
        data_dir=args.data_dir,
        dry_run=args.dry_run,
        skip_backup=args.skip_backup,
    )
    if args.dry_run:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    print(f"Importert {result['imported_files']} filer fra {args.bundle}")
    if result.get("data_backup_dir"):
        print(f"Backup av tidligere data/: {result['data_backup_dir']}")
    stats = result.get("stats") or {}
    if stats.get("activities") is not None:
        print(f"Aktiviteter i pakke: {stats['activities']}")


if __name__ == "__main__":
    main()
