"""Broad training-response half-life windows from existing lag analyses."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from .personalization_evidence_policy import PersonalizationEvidencePolicy
from .ppap_metrics_service import PpapMetricsService
from .training_response_service import TrainingResponseService


class TrainingResponseHalfLifeService:
    def __init__(self, db: Session, ppap: Optional[PpapMetricsService] = None):
        self.db = db
        self._response = TrainingResponseService(db, None, ppap)
        self._policy = PersonalizationEvidencePolicy()

    def summarize(self, *, end_date: Optional[date] = None) -> Dict[str, Any]:
        end_date = end_date or date.today()
        analysis = self._response.analyze_responses(end_date=end_date, lookback_days=270)
        by_stimulus: Dict[str, Dict[str, Any]] = {}
        for rel in analysis.get("ranking_eligible_relationships") or []:
            stim = rel.get("stimulus")
            lag = rel.get("lag_days")
            if stim is None or lag is None:
                continue
            bucket = by_stimulus.setdefault(stim, {"lags": [], "n": 0, "effects": []})
            bucket["lags"].append(int(lag))
            bucket["n"] += int(rel.get("sample_count") or 0)
            if rel.get("effect_size") is not None:
                bucket["effects"].append(abs(float(rel["effect_size"])))

        out = {}
        for stim, data in by_stimulus.items():
            lags = sorted(data["lags"])
            level = self._policy.assess(
                sample_count=data["n"],
                evidence_strength=(sum(data["effects"]) / len(data["effects"])) if data["effects"] else 0.0,
                as_of=end_date,
            )
            if not level["may_override_defaults"]:
                out[stim] = {
                    "strongest_response_window_days": None,
                    "evidence_strength": level["evidence_strength"],
                    "personalization_level": level["level"],
                    "status": "insufficient_evidence",
                }
                continue
            window = [lags[0], lags[-1]] if lags else None
            out[stim] = {
                "strongest_response_window_days": window,
                "evidence_strength": level["evidence_strength"],
                "personalization_level": level["level"],
                "status": "ok",
            }
        return {
            "as_of": end_date.isoformat(),
            "stimuli": out,
            "note": "Broad lag ranges only — not a highly parameterized model.",
        }
