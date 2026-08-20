"""Persistent coaching entities for Adaptive Coaching Engine v5.

Immutable recommendation snapshots, plan versions, feedback and availability.
JSON fields store decision context — not a table per metric.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base


class RecommendationRecord(Base):
    """Immutable snapshot of a live recommendation. Never rewrite snapshot fields."""

    __tablename__ = "recommendation_records"
    __table_args__ = (
        Index("idx_rec_as_of_active", "as_of_date", "is_active"),
        Index("idx_rec_generated_at", "generated_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    generated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    as_of_date = Column(Date, nullable=False, index=True)
    is_active = Column(Boolean, nullable=False, default=True)

    model_version = Column(String(64), nullable=False)
    decision_engine_version = Column(String(64), nullable=False)
    calibration_version = Column(String(64), nullable=False)
    application_version = Column(String(64), nullable=False)
    ranker_version = Column(String(32), nullable=True)
    prescription_version = Column(String(32), nullable=True)
    config_hash = Column(String(64), nullable=False)
    provenance_json = Column(JSON, nullable=True)

    goal_snapshot_json = Column(JSON, nullable=True)
    athlete_state_snapshot_json = Column(JSON, nullable=True)
    input_context_json = Column(JSON, nullable=True)
    recommended_workout_type = Column(String(64), nullable=False)
    candidate_workouts_json = Column(JSON, nullable=True)
    workout_prescription_json = Column(JSON, nullable=True)
    weekly_plan_json = Column(JSON, nullable=True)
    evidence_strength = Column(Float, nullable=True)
    recommendation_confidence = Column(Float, nullable=True)
    decision_status = Column(String(32), nullable=True)
    decision_trace_json = Column(JSON, nullable=True)
    model_health = Column(String(32), nullable=True)
    data_quality = Column(JSON, nullable=True)
    superseded_by_id = Column(Integer, ForeignKey("recommendation_records.id"), nullable=True)


class TrainingPlan(Base):
    __tablename__ = "training_plans"
    __table_args__ = (Index("idx_training_plans_week_start", "week_start"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    week_start = Column(Date, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    is_active = Column(Boolean, nullable=False, default=True)
    previous_plan_id = Column(Integer, ForeignKey("training_plans.id"), nullable=True)
    current_version_id = Column(
        Integer,
        ForeignKey("training_plan_versions.id", use_alter=True, name="fk_plans_current_version"),
        nullable=True,
    )
    current_version = relationship(
        "TrainingPlanVersion",
        foreign_keys=[current_version_id],
        post_update=True,
    )
    versions = relationship(
        "TrainingPlanVersion",
        back_populates="plan",
        foreign_keys="TrainingPlanVersion.plan_id",
    )


class TrainingPlanVersion(Base):
    __tablename__ = "training_plan_versions"
    __table_args__ = (UniqueConstraint("plan_id", "version", name="uq_plan_version"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(Integer, ForeignKey("training_plans.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    previous_version_id = Column(Integer, ForeignKey("training_plan_versions.id"), nullable=True)
    recommendation_id = Column(Integer, ForeignKey("recommendation_records.id"), nullable=True)
    sessions_json = Column(JSON, nullable=True)
    week_objective = Column(String(255), nullable=True)
    changes_json = Column(JSON, nullable=True)
    reason_json = Column(JSON, nullable=True)
    simulation_json = Column(JSON, nullable=True)
    scores_json = Column(JSON, nullable=True)
    plan = relationship("TrainingPlan", back_populates="versions", foreign_keys=[plan_id])


class AthleteFeedback(Base):
    __tablename__ = "athlete_feedback"
    __table_args__ = (Index("idx_feedback_activity", "activity_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    activity_id = Column(String(255), ForeignKey("activities.activity_id"), nullable=False)
    recorded_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    rpe = Column(Integer, nullable=True)
    session_feel = Column(String(32), nullable=True)
    legs = Column(String(32), nullable=True)
    pain = Column(Integer, nullable=True)
    motivation = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)


class RecommendationExecution(Base):
    __tablename__ = "recommendation_executions"
    __table_args__ = (
        Index("idx_exec_recommendation", "recommendation_id"),
        Index("idx_exec_activity", "activity_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    recommendation_id = Column(Integer, ForeignKey("recommendation_records.id"), nullable=True)
    activity_id = Column(String(255), ForeignKey("activities.activity_id"), nullable=True)
    linked_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    execution_status = Column(String(32), nullable=False)
    planned_type = Column(String(64), nullable=True)
    actual_type = Column(String(64), nullable=True)
    planned_duration = Column(Float, nullable=True)
    actual_duration = Column(Float, nullable=True)
    intensity_adherence_json = Column(JSON, nullable=True)
    structure_adherence_json = Column(JSON, nullable=True)
    overall_adherence = Column(Float, nullable=True)
    analysis_json = Column(JSON, nullable=True)


class CalibrationSnapshot(Base):
    __tablename__ = "calibration_snapshots"
    __table_args__ = (Index("idx_cal_snap_param_at", "parameter", "calculated_at"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    parameter = Column(String(64), nullable=False)
    effective_value_json = Column(JSON, nullable=True)
    default_value_json = Column(JSON, nullable=True)
    personalized_value_json = Column(JSON, nullable=True)
    use_personalized = Column(Boolean, nullable=False, default=False)
    sample_count = Column(Integer, nullable=False, default=0)
    confidence = Column(Float, nullable=True)
    calculated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    as_of_date = Column(Date, nullable=True)
    history_window_days = Column(Integer, nullable=True)
    method = Column(String(128), nullable=True)
    threshold_source = Column(String(32), nullable=True)


class TrainingAvailability(Base):
    """Weekday template (date IS NULL) or a specific date override."""

    __tablename__ = "training_availability"
    __table_args__ = (
        Index("idx_avail_weekday", "weekday"),
        Index("idx_avail_date", "date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    weekday = Column(String(16), nullable=True)
    date = Column(Date, nullable=True)
    available = Column(Boolean, nullable=False, default=True)
    max_duration_min = Column(Integer, nullable=True)
    preferred_session_types_json = Column(JSON, nullable=True)
    avoid_hard = Column(Boolean, nullable=False, default=False)
    allows_long_run = Column(Boolean, nullable=True)
    reason = Column(String(255), nullable=True)


class TrainingExperiment(Base):
    __tablename__ = "training_experiments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    hypothesis = Column(Text, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    intervention_json = Column(JSON, nullable=True)
    baseline_json = Column(JSON, nullable=True)
    metric_outcomes_json = Column(JSON, nullable=True)
    stop_conditions_json = Column(JSON, nullable=True)
    status = Column(String(32), nullable=False, default="draft")
    user_confirmed = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    notes = Column(Text, nullable=True)
