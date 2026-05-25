#!/usr/bin/env python3
"""Bounded autoresearch-style evaluator for Treningsanalyse backend sync quality.

This adapts the Karpathy/autoresearch pattern to a codebase with deterministic
checks. It does not mutate code by itself, but it provides the measurement,
state, and logging loop needed for iterative self-improvement.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
STATE_DIR = REPO_ROOT / ".autoresearch" / "sync-quality"
STATE_FILE = STATE_DIR / "state.json"
PROMPT_FILE = STATE_DIR / "prompt.txt"
BEST_PROMPT_FILE = STATE_DIR / "best_prompt.txt"
RESULTS_FILE = STATE_DIR / "results.jsonl"

DEFAULT_PROMPT = """Target: sync robustness and regression protection
Scope: backend sync flow, lactate-threshold history, and health data endpoints
Context: Preserve historical lactate-threshold observations, avoid destructive backfills, keep weekly sync safe, and protect with deterministic tests.

Improvement directions:
- Prefer deterministic command-based checks over subjective review.
- Add tests before changing sync behavior.
- Preserve historical values unless a field is missing.
- Favor bounded, reversible edits that improve sync safety or observability.
"""


@dataclass
class Criterion:
    key: str
    description: str
    command: str


CRITERIA = [
    Criterion(
        key="backend_unittests",
        description="Backend unit tests pass",
        command="./.venv/bin/python -m unittest discover -s tests -v",
    ),
    Criterion(
        key="backend_unittests_warning_free",
        description="Backend unit tests are free of warnings under PYTHONWARNINGS=default",
        command="PYTHONWARNINGS=default ./.venv/bin/python -m unittest discover -s tests -v 2>&1 | tee /tmp/treningsanalyse_backend_unittest_warnings.log && ! grep -Eiq 'warning|deprecated' /tmp/treningsanalyse_backend_unittest_warnings.log",
    ),
    Criterion(
        key="backend_compileall",
        description="Backend app compiles cleanly",
        command="./.venv/bin/python -m compileall app",
    ),
    Criterion(
        key="lactate_threshold_history_api",
        description="History API endpoint exists",
        command="grep -q 'lactate-threshold/history' app/routers/health.py",
    ),
    Criterion(
        key="preserve_existing_threshold_values",
        description="Existing lactate-threshold values are preserved unless missing",
        command="grep -q 'if activity.lactate_threshold_speed is None' app/services/sync_modules/metrics_service.py",
    ),
    Criterion(
        key="history_tests_present",
        description="Regression tests exist for lactate-threshold history behavior",
        command="grep -q 'class LactateThresholdHistoryTests' tests/test_lactate_threshold_history.py",
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
                    "target": "sync robustness and regression protection",
                    "scope": "backend sync flow, lactate-threshold history, health endpoints",
                    "context": "Treningsanalyse backend",
                    "max_score": len(CRITERIA),
                    "criteria_count": len(CRITERIA),
                    "batch_size": 1,
                    "validation_items": [
                        "backend/app/services/sync_service.py",
                        "backend/app/services/sync_modules/metrics_service.py",
                        "backend/app/routers/health.py",
                        "backend/tests/test_lactate_threshold_history.py",
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
        proc = subprocess.run(
            command,
            cwd=BACKEND_DIR,
            shell=True,
            text=True,
            capture_output=True,
        )
        attempts.append(
            {
                "attempt": attempt + 1,
                "returncode": proc.returncode,
                "stdout": proc.stdout[-4000:],
                "stderr": proc.stderr[-4000:],
            }
        )
        if proc.returncode == 0:
            return {
                "pass": True,
                "flaky": attempt == 1,
                "attempts": attempts,
            }
    return {
        "pass": False,
        "flaky": False,
        "attempts": attempts,
    }


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
