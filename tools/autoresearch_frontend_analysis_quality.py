#!/usr/bin/env python3
"""Bounded autoresearch loop for frontend, analysis and build quality."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = REPO_ROOT / ".autoresearch" / "frontend-analysis-quality"
STATE_FILE = STATE_DIR / "state.json"
PROMPT_FILE = STATE_DIR / "prompt.txt"
BEST_PROMPT_FILE = STATE_DIR / "best_prompt.txt"
RESULTS_FILE = STATE_DIR / "results.jsonl"
FRONTEND_DIR = REPO_ROOT / "frontend"
BACKEND_DIR = REPO_ROOT / "backend"

DEFAULT_PROMPT = """Target: frontend, analysis and build quality
Scope: Next.js frontend, sync status typing, analysis surfaces, and build reliability
Context: Prefer deterministic checks. Keep the dashboard buildable, typed, and safe when sync/analysis payloads evolve.
"""


@dataclass
class Criterion:
    key: str
    description: str
    command: str
    cwd: Path


CRITERIA = [
    Criterion(
        key="frontend_lint",
        description="Frontend lint completes without warnings or errors",
        command="npm run lint -- --no-cache 2>&1 | tee /tmp/treningsanalyse_frontend_lint.log && grep -q 'No ESLint warnings or errors' /tmp/treningsanalyse_frontend_lint.log",
        cwd=FRONTEND_DIR,
    ),
    Criterion(
        key="frontend_build",
        description="Frontend production build succeeds",
        command="npm run build",
        cwd=FRONTEND_DIR,
    ),
    Criterion(
        key="backend_unittests",
        description="Backend unit tests still pass after frontend/analysis changes",
        command="./.venv/bin/python -m unittest discover -s tests -v",
        cwd=BACKEND_DIR,
    ),
    Criterion(
        key="sync_status_types_present",
        description="Typed sync result payloads exist in frontend",
        command="grep -q 'export interface SyncJobResultPayload' src/types/syncJob.ts && grep -q 'SyncSummaryPayload' src/types/syncJob.ts",
        cwd=FRONTEND_DIR,
    ),
    Criterion(
        key="analysis_pages_present",
        description="Core analysis pages are present",
        command="test -f src/app/training-stress/page.tsx && test -f src/app/ukesanalyse/page.tsx && test -f src/app/statistikk/page.tsx",
        cwd=FRONTEND_DIR,
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
                    "target": "frontend, analysis and build quality",
                    "scope": "Next.js frontend, sync status typing, analysis pages",
                    "context": "Treningsanalyse frontend and analysis surfaces",
                    "max_score": len(CRITERIA),
                    "criteria_count": len(CRITERIA),
                    "batch_size": 1,
                    "validation_items": [
                        "frontend/src/components/DataSyncPanel.tsx",
                        "frontend/src/types/syncJob.ts",
                        "frontend/src/app/training-stress/page.tsx",
                        "frontend/src/app/statistikk/page.tsx",
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
