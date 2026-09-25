"""One prospective coaching observation per decision chain.

Production evidence uses the canonical chain tip. Shadow rows and superseded
predecessors are not independent samples. RecommendationExecution is the
authoritative link to an activity when it exists.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..database.models.activity import Activity
from ..database.models.coaching_v5 import AthleteFeedback, RecommendationExecution, RecommendationRecord
from ..utils.activity_filters import is_running_activity
from .athlete_feedback_service import feedback_on_or_before
from .outcome_maturity import (
    EVALUATED,
    PENDING,
    SHORT_TERM_LAG_DAYS,
    execution_maturity,
)
from .recommendation_utility_evaluator import RecommendationUtilityEvaluator

EXPLICIT_MATCH_CONFIDENCE = 1.0
LEGACY_SAME_DAY_CONFIDENCE = 0.45
LEGACY_NEARBY_CONFIDENCE = 0.3
EXPLICIT_EVIDENCE_WEIGHT = 1.0
LEGACY_EVIDENCE_WEIGHT = 0.35
SCHEMA = "canonical-prospective-observation-1"

_EXECUTION_KNOWN = {"followed", "modified", "replaced", "skipped", "unplanned", "missed", "completed", "partial"}
_IN_CHUNK = 400
_CLOSURE_ROUNDS = 32


def _aware(value: Optional[datetime]) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _tip_key(record: RecommendationRecord) -> tuple:
    return (1 if record.is_active else 0, _aware(record.generated_at), int(record.id or 0))


class CanonicalProspectiveObservationService:
    """Resolve RecommendationRecord rows into canonical prospective observations."""

    def __init__(self, db: Session):
        self.db = db

    def resolve(
        self,
        *,
        start: Optional[date] = None,
        end: Optional[date] = None,
        today: Optional[date] = None,
        include_shadow: bool = False,
    ) -> List[Dict[str, Any]]:
        today = today or date.today()
        # An as_of_date filter that drops supersede partners can publish a
        # predecessor as its own observation. Windowed loads therefore seed on
        # the window and walk superseded_by_id until every touched chain is
        # closed. The window is applied after the chain tip is chosen.
        records = self._load_records(start=start, end=end, include_shadow=include_shadow)
        observations = self._canonicalize(records, today=today, start=start, end=end)
        if start is not None:
            observations = [row for row in observations if row["as_of_date"] >= start.isoformat()]
        if end is not None:
            observations = [row for row in observations if row["as_of_date"] <= end.isoformat()]
        observations.sort(key=lambda row: (row["as_of_date"], row["recommendation_id"]), reverse=True)
        return observations

    def resolve_one(
        self,
        record_id: int,
        *,
        today: Optional[date] = None,
    ) -> Optional[Dict[str, Any]]:
        """Observation for the chain that contains record_id.

        The returned recommendation is the canonical tip, even when record_id
        is an older superseded snapshot.
        """
        today = today or date.today()
        requested = (
            self.db.query(RecommendationRecord)
            .filter(RecommendationRecord.id == record_id)
            .first()
        )
        if requested is None:
            return None
        if requested.is_shadow:
            return {
                "schema": SCHEMA,
                "recommendation_id": requested.id,
                "requested_record_id": record_id,
                "as_of_date": requested.as_of_date.isoformat(),
                "canonical": False,
                "is_shadow": True,
                "excluded_reason": "shadow_recommendation",
                "observation_status": "excluded",
                "ledger_quality": "shadow_excluded_from_production",
            }
        observations = self.resolve(today=today, include_shadow=False)
        for row in observations:
            if record_id in row["chain_member_ids"] or row["recommendation_id"] == record_id:
                payload = dict(row)
                payload["requested_record_id"] = record_id
                payload["requested_was_canonical"] = record_id == row["recommendation_id"]
                return payload
        return None

    def _load_records(
        self,
        *,
        start: Optional[date],
        end: Optional[date],
        include_shadow: bool,
    ) -> List[RecommendationRecord]:
        base = self.db.query(RecommendationRecord)
        if not include_shadow:
            base = base.filter(RecommendationRecord.is_shadow.is_(False))
        if start is None and end is None:
            return base.all()

        seed = base
        if start is not None:
            seed = seed.filter(RecommendationRecord.as_of_date >= start)
        if end is not None:
            seed = seed.filter(RecommendationRecord.as_of_date <= end)
        loaded: Dict[int, RecommendationRecord] = {row.id: row for row in seed.all()}
        for _ in range(_CLOSURE_ROUNDS):
            changed = False
            missing_targets = {
                row.superseded_by_id
                for row in loaded.values()
                if row.superseded_by_id and row.superseded_by_id not in loaded
            }
            for chunk in _chunks(missing_targets):
                for row in base.filter(RecommendationRecord.id.in_(chunk)).all():
                    if row.id not in loaded:
                        loaded[row.id] = row
                        changed = True
            for chunk in _chunks(list(loaded)):
                rows = base.filter(RecommendationRecord.superseded_by_id.in_(chunk)).all()
                for row in rows:
                    if row.id not in loaded:
                        loaded[row.id] = row
                        changed = True
            if not changed:
                break
        return list(loaded.values())

    def _canonicalize(
        self,
        records: Sequence[RecommendationRecord],
        *,
        today: date,
        start: Optional[date] = None,
        end: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        components = _components(records)
        record_ids = [row.id for row in records if row.id is not None]
        executions = self._executions_for_ids(record_ids)
        extra_activity_ids = {row.activity_id for row in executions.values() if row.activity_id}
        span_start, span_end = _activity_span(records, start=start, end=end)
        activities = self._activities_for_span(span_start, span_end, extra_activity_ids)
        feedback_index = self._feedback_for_activity_ids(activities.keys())
        tips: List[Dict[str, Any]] = []
        for members in components:
            tip, quality, chain_ids = _select_tip(members)
            tips.append(
                {
                    "tip": tip,
                    "members": members,
                    "quality": quality,
                    "chain_ids": chain_ids,
                }
            )

        by_day: Dict[date, List[Dict[str, Any]]] = defaultdict(list)
        for item in tips:
            by_day[item["tip"].as_of_date].append(item)

        observations: List[Dict[str, Any]] = []
        for day, group in by_day.items():
            group.sort(key=lambda item: _tip_key(item["tip"]), reverse=True)
            chosen = group[0]
            excluded_ids: List[int] = []
            quality = chosen["quality"]
            if len(group) > 1:
                quality = "multiple_unlinked_same_day"
                for other in group[1:]:
                    excluded_ids.extend(other["chain_ids"])
            observations.append(
                self._build_observation(
                    tip=chosen["tip"],
                    chain_ids=chosen["chain_ids"],
                    ledger_quality=quality,
                    excluded_ids=excluded_ids,
                    executions=executions,
                    activities=activities,
                    feedback_index=feedback_index,
                    today=today,
                    as_of=day,
                )
            )
        return observations

    def _build_observation(
        self,
        *,
        tip: RecommendationRecord,
        chain_ids: List[int],
        ledger_quality: str,
        excluded_ids: List[int],
        executions: Dict[int, RecommendationExecution],
        activities: Dict[str, Activity],
        feedback_index: Dict[str, List[AthleteFeedback]],
        today: date,
        as_of: date,
    ) -> Dict[str, Any]:
        execution = _execution_for_chain(chain_ids, executions, preferred_id=tip.id)
        match_source = "none"
        match_confidence = 0.0
        match_reason = "no activity link"
        evidence_weight = 0.0
        activity_id = None
        actual_type = None
        actual_load = None
        execution_status = None
        adherence = None
        execution_id = None

        if execution is not None:
            execution_id = execution.id
            activity_id = execution.activity_id
            actual_type = execution.actual_type
            adherence = execution.overall_adherence
            execution_status = (execution.execution_status or "").lower() or None
            match_source = "explicit_execution"
            match_confidence = EXPLICIT_MATCH_CONFIDENCE
            if execution.recommendation_id == tip.id:
                match_reason = "RecommendationExecution linked to the canonical recommendation"
            else:
                match_reason = (
                    f"RecommendationExecution linked to chain member {execution.recommendation_id}"
                )
            evidence_weight = EXPLICIT_EVIDENCE_WEIGHT
            if activity_id and activity_id in activities:
                actual_load = _activity_load(activities[activity_id])
                if actual_type is None:
                    actual_type = _session_hint(activities[activity_id])
        else:
            legacy = self._legacy_activity(as_of, activities)
            window_open = execution_maturity(as_of, today, has_outcome=False) == PENDING
            if window_open:
                execution_status = "pending"
                match_source = "none"
                match_confidence = 0.0
                match_reason = "execution window still open; missing activity is not a skip"
                evidence_weight = 0.0
            elif legacy is not None:
                activity, why, confidence = legacy
                activity_id = activity.activity_id
                actual_load = _activity_load(activity)
                actual_type = _session_hint(activity)
                execution_status = _legacy_execution_status(tip.recommended_workout_type, actual_type)
                match_source = "legacy_heuristic"
                match_confidence = confidence
                match_reason = why
                evidence_weight = LEGACY_EVIDENCE_WEIGHT
                ledger_quality = _join_quality(ledger_quality, "legacy_execution_link")
            else:
                execution_status = "skipped"
                match_source = "legacy_heuristic"
                match_confidence = 0.2
                match_reason = "execution window closed with no RecommendationExecution and no running activity"
                evidence_weight = LEGACY_EVIDENCE_WEIGHT
                ledger_quality = _join_quality(ledger_quality, "legacy_execution_link")

        has_execution_outcome = execution_status in _EXECUTION_KNOWN or execution_status == "skipped"
        # pending is not an evaluated outcome
        if execution_status == "pending":
            observation_status = PENDING
            exec_maturity = PENDING
        elif execution_status in _EXECUTION_KNOWN or execution_status == "skipped":
            observation_status = EVALUATED
            exec_maturity = execution_maturity(as_of, today, has_outcome=True)
            if exec_maturity == PENDING:
                # Explicit link can exist before the calendar day ends.
                observation_status = EVALUATED
                exec_maturity = EVALUATED
        else:
            observation_status = execution_maturity(as_of, today, has_outcome=has_execution_outcome)
            exec_maturity = observation_status

        feedback = self._feedback_for_activity(
            activity_id,
            as_of=as_of,
            today=today,
            feedback_index=feedback_index,
        )
        return {
            "schema": SCHEMA,
            "recommendation_id": tip.id,
            "as_of_date": as_of.isoformat(),
            "generated_at": tip.generated_at.isoformat() if tip.generated_at else None,
            "canonical": True,
            "supersede_chain_length": len(chain_ids),
            "chain_member_ids": list(chain_ids),
            "same_day_excluded_ids": excluded_ids,
            "execution_id": execution_id,
            "activity_id": activity_id,
            "observation_status": observation_status,
            "maturity_status": {
                "execution": exec_maturity if execution_status != "pending" else PENDING,
            },
            "recommended_workout_type": tip.recommended_workout_type,
            "decision_status": tip.decision_status,
            "decision_confidence": tip.decision_confidence,
            "evidence_strength": tip.evidence_strength,
            "data_quality_score": tip.data_quality_score,
            "is_active": bool(tip.is_active),
            "is_shadow": False,
            "execution_status": execution_status,
            "actual_type": actual_type,
            "actual_load": actual_load,
            "overall_adherence": float(adherence) if adherence is not None else None,
            "match_source": match_source,
            "match_confidence": match_confidence,
            "match_reason": match_reason,
            "evidence_weight": evidence_weight,
            "ledger_quality": ledger_quality,
            "provenance_json": tip.provenance_json if isinstance(tip.provenance_json, dict) else {},
            "subjective_feedback": feedback,
        }

    def _executions_for_ids(self, recommendation_ids: Sequence[int]) -> Dict[int, RecommendationExecution]:
        chosen: Dict[int, RecommendationExecution] = {}
        if not recommendation_ids:
            return chosen
        for chunk in _chunks(recommendation_ids):
            rows = (
                self.db.query(RecommendationExecution)
                .filter(RecommendationExecution.recommendation_id.in_(chunk))
                .all()
            )
            for row in rows:
                current = chosen.get(row.recommendation_id)
                if current is None or (_aware(row.linked_at), row.id or 0) >= (
                    _aware(current.linked_at),
                    current.id or 0,
                ):
                    chosen[row.recommendation_id] = row
        return chosen

    def _activities_for_span(
        self,
        start: Optional[date],
        end: Optional[date],
        extra_ids: Iterable[str],
    ) -> Dict[str, Activity]:
        rows: List[Activity] = []
        query = self.db.query(Activity).options(joinedload(Activity.activity_type))
        filters = []
        if start is not None:
            filters.append(func.date(Activity.start_time) >= start)
        if end is not None:
            filters.append(func.date(Activity.start_time) <= end)
        if filters:
            rows.extend(query.filter(*filters).all())
        have = {row.activity_id for row in rows}
        missing = [activity_id for activity_id in extra_ids if activity_id and activity_id not in have]
        for chunk in _chunks(missing):
            rows.extend(query.filter(Activity.activity_id.in_(chunk)).all())
        return {row.activity_id: row for row in rows}

    def _legacy_activity(
        self,
        as_of: date,
        activities: Dict[str, Activity],
    ) -> Optional[tuple]:
        running = [row for row in activities.values() if row.start_time is not None and is_running_activity(row)]
        same_day = [
            row
            for row in running
            if row.start_time.date() == as_of
        ]
        same_day.sort(key=lambda row: row.start_time)
        if same_day:
            return (
                same_day[0],
                "legacy same-calendar-day running activity; no RecommendationExecution",
                LEGACY_SAME_DAY_CONFIDENCE,
            )
        nearby = [
            row
            for row in running
            if as_of < row.start_time.date() <= as_of + timedelta(days=3)
        ]
        nearby.sort(key=lambda row: row.start_time)
        if nearby:
            return (
                nearby[0],
                "legacy next running activity within 3 days; no RecommendationExecution",
                LEGACY_NEARBY_CONFIDENCE,
            )
        return None

    def _feedback_for_activity_ids(self, activity_ids: Iterable[str]) -> Dict[str, List[AthleteFeedback]]:
        grouped: Dict[str, List[AthleteFeedback]] = defaultdict(list)
        ids = [str(activity_id) for activity_id in activity_ids if activity_id]
        if not ids:
            return grouped
        for chunk in _chunks(ids):
            rows = (
                self.db.query(AthleteFeedback)
                .filter(AthleteFeedback.activity_id.in_(chunk))
                .order_by(AthleteFeedback.recorded_at.desc(), AthleteFeedback.id.desc())
                .all()
            )
            for row in rows:
                grouped[str(row.activity_id)].append(row)
        return grouped

    def _feedback_for_activity(
        self,
        activity_id: Optional[str],
        *,
        as_of: date,
        today: date,
        feedback_index: Dict[str, List[AthleteFeedback]],
    ) -> Optional[Dict[str, Any]]:
        """Latest feedback that existed by the short-term cutoff.

        Feedback recorded after min(today, as_of + SHORT_TERM_LAG_DAYS) is not
        part of this observation. A missing row stays missing. The index is
        loaded once per resolve and is already newest-first.
        """
        if not activity_id:
            return None
        cutoff = min(today, as_of + timedelta(days=SHORT_TERM_LAG_DAYS))
        row = next(
            (
                item
                for item in feedback_index.get(str(activity_id), [])
                if feedback_on_or_before(item.recorded_at, cutoff)
            ),
            None,
        )
        if row is None:
            return None
        return {
            "id": row.id,
            "activity_id": row.activity_id,
            "recorded_at": row.recorded_at.isoformat() if row.recorded_at else None,
            "rpe": row.rpe,
            "pain": row.pain,
            "session_feel": row.session_feel,
            "legs": row.legs,
            "motivation": row.motivation,
            "provenance": "athlete_feedback",
            "ground_truth": False,
            "replaces_objective_data": False,
            "note": "Subjective signal only. Does not replace Garmin markers or define the outcome.",
        }


def _chunks(values: Iterable, size: int = _IN_CHUNK) -> Iterable[list]:
    chunk: list = []
    for value in values:
        chunk.append(value)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def _activity_span(
    records: Sequence[RecommendationRecord],
    *,
    start: Optional[date],
    end: Optional[date],
) -> tuple:
    """Date span for legacy activity matching.

    A requested window stays the window: tips outside it are discarded after
    chain selection, so their activities are not required. Unbounded resolve
    uses the loaded recommendations' own as_of span plus the 3-day legacy look.
    """
    if start is not None or end is not None:
        upper = end + timedelta(days=3) if end is not None else None
        lower = start
        if lower is None or upper is None:
            dates = [row.as_of_date for row in records if row.as_of_date is not None]
            if dates and lower is None:
                lower = min(dates)
            if dates and upper is None:
                upper = max(dates) + timedelta(days=3)
        return lower, upper
    dates = [row.as_of_date for row in records if row.as_of_date is not None]
    if not dates:
        return None, None
    return min(dates), max(dates) + timedelta(days=3)


def _components(records: Sequence[RecommendationRecord]) -> List[List[RecommendationRecord]]:
    by_id = {row.id: row for row in records}
    parent = {row.id: row.id for row in records}

    def find(node_id: int) -> int:
        while parent[node_id] != node_id:
            parent[node_id] = parent[parent[node_id]]
            node_id = parent[node_id]
        return node_id

    def union(left: int, right: int) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    for row in records:
        target = row.superseded_by_id
        if target is None or target == row.id or target not in by_id:
            continue
        union(row.id, target)

    groups: Dict[int, List[RecommendationRecord]] = defaultdict(list)
    for row in records:
        groups[find(row.id)].append(row)
    return list(groups.values())


def _select_tip(members: Sequence[RecommendationRecord]) -> tuple:
    ids = {row.id for row in members}
    broken = False
    natural_tips = []
    broken_tips = []
    for row in members:
        target = row.superseded_by_id
        if target is None:
            natural_tips.append(row)
        elif target == row.id or target not in ids:
            broken = True
            broken_tips.append(row)
    if natural_tips:
        pool = natural_tips
    elif broken_tips:
        pool = broken_tips
        broken = True
    else:
        pool = list(members)
        broken = True
    tip = max(pool, key=_tip_key)
    chain_ids = _chain_member_ids(tip, members)
    if broken and not natural_tips:
        quality = "incomplete_supersede_graph"
    elif broken:
        quality = "incomplete_supersede_graph"
    else:
        quality = "ok"
    return tip, quality, chain_ids


def _chain_member_ids(tip: RecommendationRecord, members: Sequence[RecommendationRecord]) -> List[int]:
    successors: Dict[int, List[RecommendationRecord]] = defaultdict(list)
    for row in members:
        if row.superseded_by_id:
            successors[row.superseded_by_id].append(row)
    seen = set()
    stack = [tip.id]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        for pred in successors.get(current, []):
            stack.append(pred.id)
    if tip.id not in seen:
        seen.add(tip.id)
    # Stable order: tip first, then remaining ids.
    rest = sorted(node_id for node_id in seen if node_id != tip.id)
    return [tip.id, *rest]


def _execution_for_chain(
    chain_ids: Iterable[int],
    executions: Dict[int, RecommendationExecution],
    *,
    preferred_id: int,
) -> Optional[RecommendationExecution]:
    if preferred_id in executions:
        return executions[preferred_id]
    found = [executions[node_id] for node_id in chain_ids if node_id in executions]
    if not found:
        return None
    found.sort(key=lambda row: (_aware(row.linked_at), row.id or 0), reverse=True)
    return found[0]


def _activity_load(activity: Activity) -> Optional[float]:
    if activity.training_stress_score is not None:
        return float(activity.training_stress_score)
    if activity.epoc is not None:
        return float(activity.epoc)
    return None


def _session_hint(activity: Activity) -> Optional[str]:
    activity_type = getattr(activity, "activity_type", None)
    if activity_type is not None and getattr(activity_type, "type_key", None):
        return activity_type.type_key
    return None


def _legacy_execution_status(recommended: Optional[str], actual: Optional[str]) -> str:
    if not actual:
        return "unknown"
    if recommended == "rest":
        return "replaced"
    family = RecommendationUtilityEvaluator.SESSION_FAMILIES.get(recommended or "", {recommended})
    if actual == recommended:
        return "followed"
    if actual in family:
        return "modified"
    return "replaced"


def _join_quality(current: str, extra: str) -> str:
    if current in {None, "", "ok"}:
        return extra
    if extra in current:
        return current
    return f"{current}+{extra}"
