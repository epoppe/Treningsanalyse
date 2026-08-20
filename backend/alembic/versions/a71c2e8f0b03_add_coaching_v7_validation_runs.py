"""add_coaching_v7_validation_runs

Revision ID: a71c2e8f0b03
Revises: f62b1c9d0e02
Create Date: 2026-08-20 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a71c2e8f0b03"
down_revision: Union[str, Sequence[str], None] = "f62b1c9d0e02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "validation_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("model_key", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("config_hash", sa.String(length=64), nullable=False),
        sa.Column("data_start", sa.Date(), nullable=False),
        sa.Column("data_end", sa.Date(), nullable=False),
        sa.Column("fold_definition_json", sa.JSON(), nullable=True),
        sa.Column("metrics_json", sa.JSON(), nullable=True),
        sa.Column("baseline_metrics_json", sa.JSON(), nullable=True),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("validation_code_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
        sa.Column("reproducibility_bundle_json", sa.JSON(), nullable=True),
        sa.Column("result_fingerprint", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_validation_runs_model", "validation_runs", ["model_key", "model_version"])
    op.create_index("idx_validation_runs_created", "validation_runs", ["created_at"])

    with op.batch_alter_table("coaching_model_registry") as batch_op:
        batch_op.add_column(sa.Column("validation_run_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_registry_validation_run",
            "validation_runs",
            ["validation_run_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("coaching_model_registry") as batch_op:
        batch_op.drop_constraint("fk_registry_validation_run", type_="foreignkey")
        batch_op.drop_column("validation_run_id")
    op.drop_index("idx_validation_runs_created", table_name="validation_runs")
    op.drop_index("idx_validation_runs_model", table_name="validation_runs")
    op.drop_table("validation_runs")
