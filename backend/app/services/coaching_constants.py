"""Canonical coaching constants — one place for shared cliffs (safety vs heuristic)."""

from __future__ import annotations

# SAFETY — hard guardrails (do not smooth away)
READINESS_REST_FLOOR = 35.0
TSB_RECOVERY_FLOOR = -25.0
HARD_DAYS_7D_MAX = 3
MONOTONY_HIGH = 2.0
MONOTONY_PROGRESSION_BLOCK = 2.2  # slightly stricter for load increases
RAPID_LOAD_RATIO = 1.5

# HEURISTIC — prefer hysteresis / continuous where possible
READINESS_QUALITY_FLOOR = 55.0
READINESS_HIGH = 75.0
EVIDENCE_ABSTAIN = 0.35
EVIDENCE_WEAK = 0.5
EVIDENCE_RANKER_FALLBACK = 0.4
RANKER_CLOSE_GAP = 8.0
HYSTERESIS_READINESS = 2.0
HYSTERESIS_TSB = 1.5
