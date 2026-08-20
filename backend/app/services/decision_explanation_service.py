"""Compact DecisionExplanation — explainability without verbose internals."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .coaching_reason_codes import REASON_DOCS, ReasonCode, map_trace_item
from .freshness_policy import FreshnessPolicy
from .metric_registry import lineage


class DecisionExplanationService:
    def build(
        self,
        recommendation: Dict[str, Any],
        *,
        context: Optional[Dict[str, Any]] = None,
        as_of: Optional[str] = None,
    ) -> Dict[str, Any]:
        context = context or {}
        trace = recommendation.get("decision_trace") or []
        reasons: List[Dict[str, Any]] = []
        guardrails: List[str] = []
        for item in trace:
            code = map_trace_item(item) or ReasonCode.DEFAULT_AEROBIC.value
            impact = self._impact_from_effect(item.get("effect"))
            entry = {
                "code": code,
                "impact": impact,
                "evidence_strength": item.get("confidence")
                or recommendation.get("evidence_strength"),
                "doc": REASON_DOCS.get(code),
                "factor": item.get("factor"),
            }
            reasons.append(entry)
            if self._is_guardrail(code, item.get("effect")):
                guardrails.append(code)

        status = recommendation.get("decision_status")
        if status in {"abstain", "insufficient_data"}:
            guardrails.append(ReasonCode.ABSTAIN_LOW_EVIDENCE.value)

        contraindications = recommendation.get("contraindications") or []
        for c in contraindications:
            text = str(c).lower()
            if "pain" in text:
                guardrails.append(ReasonCode.PAIN_GUARDRAIL.value)
            if "unavailable" in text:
                guardrails.append(ReasonCode.UNAVAILABLE_DAY.value)

        # Deduplicate preserving order
        seen = set()
        top = []
        for r in reasons:
            if r["code"] in seen:
                continue
            seen.add(r["code"])
            top.append(r)
        guardrails = list(dict.fromkeys(guardrails))

        alternatives = []
        for cand in (recommendation.get("candidate_workouts") or [])[:5]:
            if not isinstance(cand, dict):
                continue
            alternatives.append(
                {
                    "workout_type": cand.get("workout_type"),
                    "eligible": cand.get("eligible"),
                    "ranking_score": cand.get("ranking_score"),
                    "ineligible_reason": cand.get("ineligible_reason"),
                }
            )

        data_freshness = {}
        for metric, age in (context.get("metric_ages") or {}).items():
            data_freshness[metric] = FreshnessPolicy.assess(metric, as_of=context.get("as_of_date"), age_days=age)

        inputs = []
        for metric in ("tsb", "readiness", "hrv_delta_pct", "lt2"):
            if metric in context:
                inputs.append(
                    lineage(
                        metric,
                        value=context.get(metric),
                        observed_at=as_of,
                        freshness=(data_freshness.get(metric) or {}).get("freshness"),
                    )
                )

        return {
            "decision": recommendation.get("workout_type"),
            "decision_status": status,
            "top_reasons": top[:6],
            "alternatives": alternatives,
            "guardrails_triggered": guardrails,
            "inputs": inputs,
            "data_freshness": data_freshness,
            "note": "Stable reason codes for explainability — not a full debug dump.",
        }

    @staticmethod
    def _impact_from_effect(effect: Optional[str]) -> float:
        if not effect:
            return 0.0
        e = effect.lower()
        if any(k in e for k in ("block", "required", "rest", "recover")):
            return -0.25
        if "limit" in e:
            return -0.15
        if "support" in e or "allow" in e or "due" in e:
            return 0.12
        if "informational" in e:
            return 0.0
        return -0.05

    @staticmethod
    def _is_guardrail(code: str, effect: Optional[str]) -> bool:
        safety = {
            ReasonCode.PAIN_GUARDRAIL.value,
            ReasonCode.UNAVAILABLE_DAY.value,
            ReasonCode.FATIGUE_EXTREME.value,
            ReasonCode.READINESS_REST.value,
            ReasonCode.HARD_DENSITY_GUARDRAIL.value,
            ReasonCode.RACE_RECOVERY.value,
        }
        if code in safety:
            return True
        e = str(effect or "").lower()
        return any(k in e for k in ("block", "required", "rest_required", "recovery_required"))
