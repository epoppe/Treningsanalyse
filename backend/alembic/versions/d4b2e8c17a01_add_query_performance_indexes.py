"""add_query_performance_indexes

Revision ID: d4b2e8c17a01
Revises: c3f8a1d92e10
Create Date: 2026-07-26 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4b2e8c17a01"
down_revision: Union[str, Sequence[str], None] = "c3f8a1d92e10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("activity_laps", schema=None) as batch_op:
        batch_op.create_index("ix_activity_laps_activity_id", ["activity_id"], unique=False)

    with op.batch_alter_table("personal_records", schema=None) as batch_op:
        batch_op.create_index("ix_personal_records_activity_id", ["activity_id"], unique=False)

    with op.batch_alter_table("sync_runs", schema=None) as batch_op:
        batch_op.create_index(
            "idx_sync_runs_status_job_type",
            ["status", "job_type"],
            unique=False,
        )

    with op.batch_alter_table("sync_jobs", schema=None) as batch_op:
        batch_op.create_index(
            "idx_sync_jobs_status_job_type",
            ["status", "job_type"],
            unique=False,
        )

    # Delvis indeks for TE-backfill (vanlig filter: manglende/ugyldig TE, sortert på start_time)
    op.create_index(
        "idx_activities_missing_training_effect",
        "activities",
        ["start_time"],
        unique=False,
        sqlite_where=sa.text(
            "(total_training_effect IS NULL OR total_training_effect <= 0)"
        ),
    )


def downgrade() -> None:
    op.drop_index("idx_activities_missing_training_effect", table_name="activities")

    with op.batch_alter_table("sync_jobs", schema=None) as batch_op:
        batch_op.drop_index("idx_sync_jobs_status_job_type")

    with op.batch_alter_table("sync_runs", schema=None) as batch_op:
        batch_op.drop_index("idx_sync_runs_status_job_type")

    with op.batch_alter_table("personal_records", schema=None) as batch_op:
        batch_op.drop_index("ix_personal_records_activity_id")

    with op.batch_alter_table("activity_laps", schema=None) as batch_op:
        batch_op.drop_index("ix_activity_laps_activity_id")
