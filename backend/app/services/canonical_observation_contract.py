"""Explicit contract for one canonical prospective observation.

The string is the version clients should branch on. REQUIRED_OBSERVATION_KEYS
is the field set that REST, MCP, and tests treat as stable for this version.
"""

from __future__ import annotations

from typing import Mapping

OBSERVATION_SCHEMA = "canonical-prospective-observation-1"

REQUIRED_OBSERVATION_KEYS = (
    "schema",
    "recommendation_id",
    "as_of_date",
    "generated_at",
    "canonical",
    "supersede_chain_length",
    "chain_member_ids",
    "same_day_excluded_ids",
    "execution_id",
    "activity_id",
    "observation_status",
    "maturity_status",
    "recommended_workout_type",
    "decision_status",
    "decision_confidence",
    "evidence_strength",
    "data_quality_score",
    "is_active",
    "is_shadow",
    "execution_status",
    "actual_type",
    "actual_load",
    "overall_adherence",
    "match_source",
    "match_confidence",
    "match_reason",
    "evidence_weight",
    "ledger_quality",
    "provenance_json",
    "subjective_feedback",
)


def missing_contract_keys(payload: Mapping[str, object]) -> list[str]:
    """Keys this schema version promises and the payload does not carry."""
    return [key for key in REQUIRED_OBSERVATION_KEYS if key not in payload]
