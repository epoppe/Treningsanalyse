"""Centralized health severity mapping — do not manually count issue strings."""

from __future__ import annotations

from typing import Dict, Iterable, List, Set

from .status_semantics import HealthStatus


# Codes → severity. Absence of a code means INFO/ignore for aggregation.
CRITICAL_CODES: Set[str] = {
    "migration_behind",
    "corrupted_recommendation_graph",
    "failed_safety_invariant",
    "supersede_cycle",
}

ATTENTION_CODES: Set[str] = {
    "stale_lt2",
    "stale_critical_speed",
    "orphan_executions",
    "active_model_lacks_validation_run",
    "active_already_superseded",
}

DEGRADED_CODES: Set[str] = {
    "low_prospective_n",
    "missing_lt2",
    "missing_hrv_baseline",
    "no_shadow_evidence",
    "no_sync_state",
    "no_validation_run",
    "missing_optional_metric",
}


class HealthStatusPolicy:
    @staticmethod
    def severity_for(code: str) -> HealthStatus:
        if code in CRITICAL_CODES:
            return HealthStatus.CRITICAL
        if code in ATTENTION_CODES:
            return HealthStatus.ATTENTION_REQUIRED
        if code in DEGRADED_CODES:
            return HealthStatus.DEGRADED
        return HealthStatus.DEGRADED

    @staticmethod
    def aggregate(codes: Iterable[str]) -> str:
        codes_list = list(codes)
        if not codes_list:
            return HealthStatus.HEALTHY.value
        severities = {HealthStatusPolicy.severity_for(c) for c in codes_list}
        if HealthStatus.CRITICAL in severities:
            return HealthStatus.CRITICAL.value
        if HealthStatus.ATTENTION_REQUIRED in severities:
            return HealthStatus.ATTENTION_REQUIRED.value
        if HealthStatus.DEGRADED in severities:
            return HealthStatus.DEGRADED.value
        return HealthStatus.HEALTHY.value

    @staticmethod
    def findings_from_codes(codes: List[str]) -> List[Dict[str, str]]:
        return [{"code": c, "severity": HealthStatusPolicy.severity_for(c).value} for c in codes]
