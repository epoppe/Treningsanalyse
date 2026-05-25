#!/usr/bin/env python3
"""Autoresearch-style evaluator for sync and local storage efficiency/robustness."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = REPO_ROOT / ".autoresearch" / "sync-storage-efficiency"
STATE_FILE = STATE_DIR / "state.json"
PROMPT_FILE = STATE_DIR / "prompt.txt"
BEST_PROMPT_FILE = STATE_DIR / "best_prompt.txt"
RESULTS_FILE = STATE_DIR / "results.jsonl"
BACKEND_DIR = REPO_ROOT / "backend"

DEFAULT_PROMPT = """Target: sync and local storage efficiency
Scope: sync throughput, FIT/parquet writes, incremental refresh, and summary updates
Context: Prefer bounded static checks that reveal likely performance and robustness bottlenecks before they become user-visible.

Improvement directions:
- Avoid full-file reloads and rewrites on hot paths.
- Prefer incremental summary refresh over full historical recomputation.
- Batch writes and commits where loops currently persist one item at a time.
- Avoid duplicate metric calculations for the same activity in the same sync flow.
- Keep efficient patterns observable with deterministic checks.
"""


@dataclass
class Criterion:
    key: str
    description: str
    command: str


CRITERIA = [
    Criterion(
        key="incremental_sync_state_present",
        description="Sync flow uses SyncState-based incremental boundaries",
        command="grep -q 'last_synced_date' app/services/sync_service.py",
    ),
    Criterion(
        key="chunked_fit_download_present",
        description="Long FIT backfills are chunked instead of one monolithic period",
        command="grep -q 'chunk_start = start_date' app/services/sync_service.py && grep -q 'chunk_end = min(chunk_start + timedelta(days=6), end_date)' app/services/sync_service.py",
    ),
    Criterion(
        key="parquet_storage_present",
        description="Local activity details are stored in parquet",
        command="grep -q 'activity_details.parquet' app/storage.py && grep -q 'to_parquet' app/storage.py",
    ),
    Criterion(
        key="no_forced_activity_details_reload",
        description="Reading one activity should not force a full parquet reload every time",
        command="""python3 - <<'PY'
from pathlib import Path
text = Path('app/storage.py').read_text()
needle = 'def get_activity_details(self, activity_id: int, force_reload: bool = False) -> Optional[pd.DataFrame]:'
start = text.index(needle)
end = text.index('def get_hrv_data', start)
block = text[start:end]
ok = 'if force_reload:' in block and 'self.reload_activity_details()' in block
raise SystemExit(0 if ok else 1)
PY""",
    ),
    Criterion(
        key="no_global_monthly_summary_rebuild_in_sync",
        description="Regular sync should not always rebuild all monthly summaries across history",
        command="! grep -q 'calculate_monthly_summaries()' app/services/sync_service.py",
    ),
    Criterion(
        key="no_parquet_write_inside_activity_loop",
        description="Main activity sync should avoid rewriting parquet inside the per-activity loop",
        command="""python3 - <<'PY'
from pathlib import Path
text = Path('app/services/sync_service.py').read_text()
loop_start = text.index('for i, act_data in enumerate(activities_to_save):')
loop_end = text.index('self.db.commit()', loop_start)
block = text[loop_start:loop_end]
raise SystemExit(0 if 'self.storage.save_activity_details(parquet_records)' not in block else 1)
PY""",
    ),
    Criterion(
        key="no_per_missing_date_commits",
        description="Missing health-date markers are batched instead of committed inside daily loops",
        command="""python3 - <<'PY'
from pathlib import Path
files = [
    Path('app/services/sync_modules/hrv_sync_service.py'),
    Path('app/services/sync_modules/sleep_sync_service.py'),
    Path('app/services/sync_modules/stress_sync_service.py'),
]
bad = False
for path in files:
    lines = path.read_text().splitlines()
    for idx, line in enumerate(lines):
        if 'HealthDataMissing(data_type=' not in line:
            continue
        window = '\\n'.join(lines[idx:idx + 8])
        if 'self.sync_service.db.commit()' in window:
            bad = True
            break
    if bad:
        break
raise SystemExit(1 if bad else 0)
PY""",
    ),
    Criterion(
        key="no_full_activity_id_scan_all",
        description="Existing activity-id lookups avoid loading the full id set with .all() on every sync",
        command="! grep -q 'db.query(Activity.activity_id).all()' app/storage.py && ! grep -q 'self.db.query(Activity.activity_id).all()' app/services/sync_service.py",
    ),
]


OPPORTUNITIES = {
    "no_forced_activity_details_reload": "Fjern full reload av activity_details.parquet i get_activity_details(); bruk in-memory cache eller lazy reload kun ved behov.",
    "no_global_monthly_summary_rebuild_in_sync": "Bytt fra global calculate_monthly_summaries() til periodeavgrenset månedsoppdatering for berørte måneder.",
    "no_parquet_write_inside_activity_loop": "Samle parquet_records for flere aktiviteter og flush dem i batch etter loopen, ikke én full parquet-skriving per aktivitet.",
    "no_per_missing_date_commits": "Batch HealthDataMissing-innsettinger og commit én gang per sync-modul i stedet for per dag uten data.",
    "no_full_activity_id_scan_all": "Erstatt full activity_id .all()-scan med mer inkrementell eksistenssjekk eller bounded query for aktuell periode.",
}


def ensure_state_files() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if not PROMPT_FILE.exists():
        PROMPT_FILE.write_text(DEFAULT_PROMPT)
    if not BEST_PROMPT_FILE.exists():
        BEST_PROMPT_FILE.write_text(PROMPT_FILE.read_text())
    if not RESULTS_FILE.exists():
        RESULTS_FILE.write_text("")
    if not STATE_FILE.exists():
        STATE_FILE.write_text(
            json.dumps(
                {
                    "best_score": -1,
                    "run_number": 0,
                    "target": "sync and local storage efficiency",
                    "scope": "sync throughput, FIT/parquet writes, incremental refresh, summary updates",
                    "context": "Treningsanalyse sync + local storage",
                    "max_score": len(CRITERIA),
                    "criteria_count": len(CRITERIA),
                    "batch_size": 1,
                    "validation_items": [
                        "backend/app/storage.py",
                        "backend/app/services/sync_service.py",
                        "backend/app/services/sync_modules/fit_sync_service.py",
                        "backend/app/services/sync_modules/hrv_sync_service.py",
                        "backend/app/services/summary_service.py",
                    ],
                    "sampled_items": [],
                    "item_failures": {},
                    "plateau_counter": 0,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


def run_command(command: str) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    for attempt in range(2):
        proc = subprocess.run(command, cwd=BACKEND_DIR, shell=True, text=True, capture_output=True)
        attempts.append(
            {
                "attempt": attempt + 1,
                "returncode": proc.returncode,
                "stdout": proc.stdout[-4000:],
                "stderr": proc.stderr[-4000:],
            }
        )
        if proc.returncode == 0:
            return {"pass": True, "flaky": attempt == 1, "attempts": attempts}
    return {"pass": False, "flaky": False, "attempts": attempts}


def main() -> int:
    ensure_state_files()
    state = json.loads(STATE_FILE.read_text())
    state["max_score"] = len(CRITERIA)
    state["criteria_count"] = len(CRITERIA)
    prompt_text = PROMPT_FILE.read_text()
    previous_best = state.get("best_score", -1)
    run_number = int(state.get("run_number", 0)) + 1

    criteria_results: dict[str, Any] = {}
    score = 0
    flaky_commands: list[str] = []
    failures: list[str] = []
    opportunities: list[str] = []

    for criterion in CRITERIA:
        result = run_command(criterion.command)
        criteria_results[criterion.key] = {
            "description": criterion.description,
            "pass": result["pass"],
            "flaky": result["flaky"],
            "command": criterion.command,
        }
        if result["pass"]:
            score += 1
        else:
            failures.append(f"{criterion.key}: {criterion.description}")
            if criterion.key in OPPORTUNITIES:
                opportunities.append(OPPORTUNITIES[criterion.key])
        if result["flaky"]:
            flaky_commands.append(criterion.key)

    status = "keep" if score >= previous_best else "discard"
    if score > previous_best:
        state["best_score"] = score
        state["plateau_counter"] = 0
        BEST_PROMPT_FILE.write_text(prompt_text)
    else:
        state["plateau_counter"] = int(state.get("plateau_counter", 0)) + 1

    state["run_number"] = run_number
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))

    entry = {
        "run": run_number,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "score": score,
        "max": len(CRITERIA),
        "status": status,
        "criteria": criteria_results,
        "prompt_text": prompt_text,
        "failures": failures,
        "opportunities": opportunities,
        "flaky_commands": flaky_commands,
    }
    with RESULTS_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(json.dumps(entry, ensure_ascii=False, indent=2))
    return 0 if score == len(CRITERIA) else 1


if __name__ == "__main__":
    raise SystemExit(main())
