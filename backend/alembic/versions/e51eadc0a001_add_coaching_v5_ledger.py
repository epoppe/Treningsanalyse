"""add_coaching_v5_ledger

Revision ID: e51eadc0a001
Revises: d4b2e8c17a01
Create Date: 2026-08-20 05:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e51eadc0a001"
down_revision: Union[str, Sequence[str], None] = "d4b2e8c17a01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recommendation_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("decision_engine_version", sa.String(length=64), nullable=False),
        sa.Column("calibration_version", sa.String(length=64), nullable=False),
        sa.Column("application_version", sa.String(length=64), nullable=False),
        sa.Column("ranker_version", sa.String(length=32), nullable=True),
        sa.Column("prescription_version", sa.String(length=32), nullable=True),
        sa.Column("config_hash", sa.String(length=64), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=True),
        sa.Column("goal_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("athlete_state_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("input_context_json", sa.JSON(), nullable=True),
        sa.Column("recommended_workout_type", sa.String(length=64), nullable=False),
        sa.Column("candidate_workouts_json", sa.JSON(), nullable=True),
        sa.Column("workout_prescription_json", sa.JSON(), nullable=True),
        sa.Column("weekly_plan_json", sa.JSON(), nullable=True),
        sa.Column("evidence_strength", sa.Float(), nullable=True),
        sa.Column("recommendation_confidence", sa.Float(), nullable=True),
        sa.Column("decision_status", sa.String(length=32), nullable=True),
        sa.Column("decision_trace_json", sa.JSON(), nullable=True),
        sa.Column("model_health", sa.String(length=32), nullable=True),
        sa.Column("data_quality", sa.JSON(), nullable=True),
        sa.Column("superseded_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["superseded_by_id"], ["recommendation_records.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_rec_as_of_active", "recommendation_records", ["as_of_date", "is_active"])
    op.create_index("idx_rec_generated_at", "recommendation_records", ["generated_at"])
    op.create_index(op.f("ix_recommendation_records_as_of_date"), "recommendation_records", ["as_of_date"])

    op.create_table(
        "training_plan_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("previous_version_id", sa.Integer(), nullable=True),
        sa.Column("recommendation_id", sa.Integer(), nullable=True),
        sa.Column("sessions_json", sa.JSON(), nullable=True),
        sa.Column("week_objective", sa.String(length=255), nullable=True),
        sa.Column("changes_json", sa.JSON(), nullable=True),
        sa.Column("reason_json", sa.JSON(), nullable=True),
        sa.Column("simulation_json", sa.JSON(), nullable=True),
        sa.Column("scores_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["previous_version_id"], ["training_plan_versions.id"]),
        sa.ForeignKeyConstraint(["recommendation_id"], ["recommendation_records.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "version", name="uq_plan_version"),
    )

    op.create_table(
        "training_plans",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("previous_plan_id", sa.Integer(), nullable=True),
        sa.Column("current_version_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["current_version_id"], ["training_plan_versions.id"], name="fk_plans_current_version"),
        sa.ForeignKeyConstraint(["previous_plan_id"], ["training_plans.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_training_plans_week_start", "training_plans", ["week_start"])

    with op.batch_alter_table("training_plan_versions") as batch_op:
        batch_op.create_foreign_key("fk_plan_versions_plan_id", "training_plans", ["plan_id"], ["id"])
        batch_op.create_index("ix_training_plan_versions_plan_id", ["plan_id"])

    op.create_table(
        "athlete_feedback",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("activity_id", sa.String(length=255), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("rpe", sa.Integer(), nullable=True),
        sa.Column("session_feel", sa.String(length=32), nullable=True),
        sa.Column("legs", sa.String(length=32), nullable=True),
        sa.Column("pain", sa.Integer(), nullable=True),
        sa.Column("motivation", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.activity_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_feedback_activity", "athlete_feedback", ["activity_id"])

    op.create_table(
        "recommendation_executions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("recommendation_id", sa.Integer(), nullable=True),
        sa.Column("activity_id", sa.String(length=255), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("execution_status", sa.String(length=32), nullable=False),
        sa.Column("planned_type", sa.String(length=64), nullable=True),
        sa.Column("actual_type", sa.String(length=64), nullable=True),
        sa.Column("planned_duration", sa.Float(), nullable=True),
        sa.Column("actual_duration", sa.Float(), nullable=True),
        sa.Column("intensity_adherence_json", sa.JSON(), nullable=True),
        sa.Column("structure_adherence_json", sa.JSON(), nullable=True),
        sa.Column("overall_adherence", sa.Float(), nullable=True),
        sa.Column("analysis_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["recommendation_id"], ["recommendation_records.id"]),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.activity_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_exec_recommendation", "recommendation_executions", ["recommendation_id"])
    op.create_index("idx_exec_activity", "recommendation_executions", ["activity_id"])

    op.create_table(
        "calibration_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("parameter", sa.String(length=64), nullable=False),
        sa.Column("effective_value_json", sa.JSON(), nullable=True),
        sa.Column("default_value_json", sa.JSON(), nullable=True),
        sa.Column("personalized_value_json", sa.JSON(), nullable=True),
        sa.Column("use_personalized", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("calculated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=True),
        sa.Column("history_window_days", sa.Integer(), nullable=True),
        sa.Column("method", sa.String(length=128), nullable=True),
        sa.Column("threshold_source", sa.String(length=32), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_cal_snap_param_at", "calibration_snapshots", ["parameter", "calculated_at"])

    op.create_table(
        "training_availability",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("weekday", sa.String(length=16), nullable=True),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("available", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("max_duration_min", sa.Integer(), nullable=True),
        sa.Column("preferred_session_types_json", sa.JSON(), nullable=True),
        sa.Column("avoid_hard", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("allows_long_run", sa.Boolean(), nullable=True),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_avail_weekday", "training_availability", ["weekday"])
    op.create_index("idx_avail_date", "training_availability", ["date"])

    op.create_table(
        "training_experiments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("hypothesis", sa.Text(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("intervention_json", sa.JSON(), nullable=True),
        sa.Column("baseline_json", sa.JSON(), nullable=True),
        sa.Column("metric_outcomes_json", sa.JSON(), nullable=True),
        sa.Column("stop_conditions_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("user_confirmed", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("training_experiments")
    op.drop_table("training_availability")
    op.drop_table("calibration_snapshots")
    op.drop_table("recommendation_executions")
    op.drop_table("athlete_feedback")
    with op.batch_alter_table("training_plans") as batch_op:
        batch_op.drop_constraint("fk_plans_current_version", type_="foreignkey")
    op.drop_table("training_plans")
    op.drop_table("training_plan_versions")
    op.drop_table("recommendation_records")
