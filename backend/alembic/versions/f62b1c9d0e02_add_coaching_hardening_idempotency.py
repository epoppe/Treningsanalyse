"""add_coaching_hardening_idempotency

Revision ID: f62b1c9d0e02
Revises: e51eadc0a001
Create Date: 2026-08-20 15:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f62b1c9d0e02"
down_revision: Union[str, Sequence[str], None] = "e51eadc0a001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("recommendation_records") as batch_op:
        batch_op.add_column(sa.Column("decision_payload_hash", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("decision_confidence", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("data_quality_score", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("is_shadow", sa.Boolean(), nullable=False, server_default=sa.text("0")))
        batch_op.add_column(sa.Column("shadow_of_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_rec_shadow_of",
            "recommendation_records",
            ["shadow_of_id"],
            ["id"],
        )
        batch_op.create_index(
            "idx_rec_idempotency",
            ["as_of_date", "config_hash", "decision_payload_hash"],
        )

    with op.batch_alter_table("training_plan_versions") as batch_op:
        batch_op.add_column(sa.Column("content_hash", sa.String(length=64), nullable=True))

    with op.batch_alter_table("recommendation_executions") as batch_op:
        batch_op.create_unique_constraint("uq_exec_rec_activity", ["recommendation_id", "activity_id"])

    op.create_table(
        "coaching_model_registry",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("model_key", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="experimental"),
        sa.Column("config_json", sa.JSON(), nullable=True),
        sa.Column("promotion_gate_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_key", "version", name="uq_model_key_version"),
    )

    op.create_table(
        "shadow_recommendations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("production_recommendation_id", sa.Integer(), nullable=True),
        sa.Column("model_key", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("production_workout_type", sa.String(length=64), nullable=True),
        sa.Column("shadow_workout_type", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("config_hash", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["production_recommendation_id"], ["recommendation_records.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_shadow_as_of", "shadow_recommendations", ["as_of_date"])


def downgrade() -> None:
    op.drop_index("idx_shadow_as_of", table_name="shadow_recommendations")
    op.drop_table("shadow_recommendations")
    op.drop_table("coaching_model_registry")
    with op.batch_alter_table("recommendation_executions") as batch_op:
        batch_op.drop_constraint("uq_exec_rec_activity", type_="unique")
    with op.batch_alter_table("training_plan_versions") as batch_op:
        batch_op.drop_column("content_hash")
    with op.batch_alter_table("recommendation_records") as batch_op:
        batch_op.drop_index("idx_rec_idempotency")
        batch_op.drop_constraint("fk_rec_shadow_of", type_="foreignkey")
        batch_op.drop_column("shadow_of_id")
        batch_op.drop_column("is_shadow")
        batch_op.drop_column("data_quality_score")
        batch_op.drop_column("decision_confidence")
        batch_op.drop_column("decision_payload_hash")
