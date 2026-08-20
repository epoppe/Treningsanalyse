"""Stable machine-readable coaching reason codes — not free-form prose."""

from __future__ import annotations

from enum import Enum
from typing import Dict, Optional


class ReasonCode(str, Enum):
    RECOVERY_LOW = "RECOVERY_LOW"
    RECOVERY_COST_HIGH = "RECOVERY_COST_HIGH"
    QUALITY_SESSION_DUE = "QUALITY_SESSION_DUE"
    QUALITY_SESSION_NOT_DUE = "QUALITY_SESSION_NOT_DUE"
    LOAD_PROGRESSING = "LOAD_PROGRESSING"
    LOAD_RAPID_INCREASE = "LOAD_RAPID_INCREASE"
    GOAL_SPECIFICITY = "GOAL_SPECIFICITY"
    PAIN_GUARDRAIL = "PAIN_GUARDRAIL"
    DATA_STALE = "DATA_STALE"
    DATA_MISSING = "DATA_MISSING"
    HARD_SESSION_SPACING = "HARD_SESSION_SPACING"
    HARD_DENSITY_GUARDRAIL = "HARD_DENSITY_GUARDRAIL"
    UNAVAILABLE_DAY = "UNAVAILABLE_DAY"
    FATIGUE_EXTREME = "FATIGUE_EXTREME"
    READINESS_REST = "READINESS_REST"
    ABSTAIN_LOW_EVIDENCE = "ABSTAIN_LOW_EVIDENCE"
    RANKER_OVERRIDE = "RANKER_OVERRIDE"
    EASY_VOLUME_PRIORITY = "EASY_VOLUME_PRIORITY"
    RACE_RECOVERY = "RACE_RECOVERY"
    DEFAULT_AEROBIC = "DEFAULT_AEROBIC"


REASON_DOCS: Dict[str, str] = {
    ReasonCode.RECOVERY_LOW.value: "Recovery markers or TSB indicate limited capacity for intensity",
    ReasonCode.RECOVERY_COST_HIGH.value: "Expected recovery cost of candidate outweighs benefit",
    ReasonCode.QUALITY_SESSION_DUE.value: "Spacing and readiness support a quality session",
    ReasonCode.QUALITY_SESSION_NOT_DUE.value: "Quality session not due given recent hard load",
    ReasonCode.LOAD_PROGRESSING.value: "Load progression within personal envelope",
    ReasonCode.LOAD_RAPID_INCREASE.value: "Recent load increase exceeds calibrated caution",
    ReasonCode.GOAL_SPECIFICITY.value: "Aligned with race capability gap or goal event",
    ReasonCode.PAIN_GUARDRAIL.value: "Pain / MS readiness blocks intensity increase",
    ReasonCode.DATA_STALE.value: "Key metric aging/stale — reduced confidence",
    ReasonCode.DATA_MISSING.value: "Missing evidence reduced confidence (not treated as negative physiology)",
    ReasonCode.HARD_SESSION_SPACING.value: "Insufficient hours since last hard session",
    ReasonCode.HARD_DENSITY_GUARDRAIL.value: "Too many hard sessions in 7 days",
    ReasonCode.UNAVAILABLE_DAY.value: "Day marked unavailable — no training scheduled",
    ReasonCode.FATIGUE_EXTREME.value: "Extreme fatigue / TSB floor — recovery required",
    ReasonCode.READINESS_REST.value: "Readiness below rest floor",
    ReasonCode.ABSTAIN_LOW_EVIDENCE.value: "Evidence too weak for assertive prescription",
    ReasonCode.RANKER_OVERRIDE.value: "Candidate ranker overrode rule cascade",
    ReasonCode.EASY_VOLUME_PRIORITY.value: "Easy volume priority for aerobic maintenance",
    ReasonCode.RACE_RECOVERY.value: "Post-race recovery constraint",
    ReasonCode.DEFAULT_AEROBIC.value: "Default aerobic maintenance when no stronger signal",
}


_TRACE_EFFECT_MAP = {
    "rest_required": ReasonCode.READINESS_REST,
    "recovery_required": ReasonCode.FATIGUE_EXTREME,
    "blocks_hard_session": ReasonCode.HARD_SESSION_SPACING,
    "limits_intensity": ReasonCode.RECOVERY_LOW,
    "hard_density": ReasonCode.HARD_DENSITY_GUARDRAIL,
    "rapid_load": ReasonCode.LOAD_RAPID_INCREASE,
    "unavailable": ReasonCode.UNAVAILABLE_DAY,
    "pain": ReasonCode.PAIN_GUARDRAIL,
    "abstain": ReasonCode.ABSTAIN_LOW_EVIDENCE,
    "informational": ReasonCode.DEFAULT_AEROBIC,
}


_FACTOR_MAP = {
    "readiness": ReasonCode.READINESS_REST,
    "tsb": ReasonCode.FATIGUE_EXTREME,
    "hard_session_spacing": ReasonCode.HARD_SESSION_SPACING,
    "hard_days_7d": ReasonCode.HARD_DENSITY_GUARDRAIL,
    "hrv_delta_pct": ReasonCode.RECOVERY_LOW,
    "rhr_delta_bpm": ReasonCode.RECOVERY_LOW,
    "rapid_load_change": ReasonCode.LOAD_RAPID_INCREASE,
    "easy_volume_7d": ReasonCode.EASY_VOLUME_PRIORITY,
    "musculoskeletal": ReasonCode.PAIN_GUARDRAIL,
}


def map_trace_item(item: Dict) -> Optional[str]:
    effect = str(item.get("effect") or "").lower()
    factor = str(item.get("factor") or "").lower()
    for key, code in _TRACE_EFFECT_MAP.items():
        if key in effect:
            return code.value
    for key, code in _FACTOR_MAP.items():
        if key in factor:
            return code.value
    if item.get("effect"):
        return ReasonCode.DEFAULT_AEROBIC.value
    return None
