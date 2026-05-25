#!/usr/bin/env python3
"""Bounded autoresearch loop for weekly sync robustness in Treningsanalyse."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = REPO_ROOT / ".autoresearch" / "weekly-sync-robustness"
STATE_FILE = STATE_DIR / "state.json"
PROMPT_FILE = STATE_DIR / "prompt.txt"
BEST_PROMPT_FILE = STATE_DIR / "best_prompt.txt"
RESULTS_FILE = STATE_DIR / "results.jsonl"
WORKSPACE_ROOT = REPO_ROOT.parent

DEFAULT_PROMPT = """Target: weekly sync robustness
Scope: scheduled training sync, threshold-history capture, cron registration, and summary integrity
Context: The Friday 23:00 weekly sync must remain safe, observable, and stable. Prefer deterministic checks, protect the JSON contract, and ensure the cron entry keeps pointing at the intended training topic.
"""


@dataclass
class Criterion:
    key: str
    description: str
    command: str
    cwd: Path


CRITERIA = [
    Criterion(
        key="weekly_sync_script_compiles",
        description="Weekly sync script compiles",
        command="python3 -m py_compile tools/training_weekly_sync.py",
        cwd=WORKSPACE_ROOT,
    ),
    Criterion(
        key="weekly_sync_smoke_outputs_json",
        description="Weekly sync smoke run returns JSON with threshold and counts",
        command="Treningsanalyse/backend/.venv/bin/python /home/erik-poppe/.openclaw/workspace/tools/training_weekly_sync.py 2>/tmp/training_weekly_sync.err | tail -n 1 | python3 -c 'import json,sys; data=json.loads(sys.stdin.read()); assert \"threshold\" in data and \"counts\" in data and \"activity_sync\" in data'",
        cwd=WORKSPACE_ROOT,
    ),
    Criterion(
        key="weekly_sync_template_present",
        description="Weekly sync template exists",
        command="grep -q 'training_weekly_sync.py' agents/templates/weekly_training_sync.md",
        cwd=WORKSPACE_ROOT,
    ),
    Criterion(
        key="weekly_sync_cron_registered",
        description="Friday 23:00 cron job is registered for weekly training sync",
        command="grep -q 'weekly_training_sync_friday_2300' /home/erik-poppe/.openclaw/cron/jobs.json && grep -Fq '0 23 * * 5' /home/erik-poppe/.openclaw/cron/jobs.json",
        cwd=REPO_ROOT,
    ),
    Criterion(
        key="threshold_history_endpoint_present",
        description="Threshold-history endpoint is still available to support the weekly job",
        command="grep -q 'lactate-threshold/history' backend/app/routers/health.py",
        cwd=REPO_ROOT,
    ),
]


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
                    "target": "weekly sync robustness",
                    "scope": "scheduled training sync and threshold-history capture",
                    "context": "Treningsanalyse automation + weekly sync",
                    "max_score": len(CRITERIA),
                    "criteria_count": len(CRITERIA),
                    "batch_size": 1,
                    "validation_items": [
                        "tools/training_weekly_sync.py",
                        "agents/templates/weekly_training_sync.md",
                        "backend/app/routers/health.py",
                        "/home/erik-poppe/.openclaw/cron/jobs.json",
                    ],
                    "sampled_items": [],
                    "item_failures": {},
                    "plateau_counter": 0,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


def run_command(command: str, cwd: Path) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    for attempt in range(2):
        proc = subprocess.run(command, cwd=cwd, shell=True, text=True, capture_output=True)
        attempts.append({
            "attempt": attempt + 1,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:],
        })
        if proc.returncode == 0:
            return {"pass": True, "flaky": attempt == 1, "attempts": attempts}
    return {"pass": False, "flaky": False, "attempts": attempts}


def main() -> int:
    ensure_state_files()
    state = json.loads(STATE_FILE.read_text())
    prompt_text = PROMPT_FILE.read_text()
    previous_best = state.get("best_score", -1)
    run_number = int(state.get("run_number", 0)) + 1

    criteria_results: dict[str, Any] = {}
    score = 0
    flaky_commands: list[str] = []
    failures: list[str] = []

    for criterion in CRITERIA:
        result = run_command(criterion.command, criterion.cwd)
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
        "flaky_commands": flaky_commands,
    }
    with RESULTS_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(json.dumps(entry, ensure_ascii=False, indent=2))
    return 0 if score == len(CRITERIA) else 1


if __name__ == "__main__":
    raise SystemExit(main())
