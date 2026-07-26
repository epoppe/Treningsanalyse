"""add_sync_run_checkpoint

Revision ID: c3f8a1d92e10
Revises: 420b721e1bf8
Create Date: 2026-07-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3f8a1d92e10"
down_revision: Union[str, Sequence[str], None] = "420b721e1bf8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("sync_runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("checkpoint", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("sync_runs", schema=None) as batch_op:
        batch_op.drop_column("checkpoint")
