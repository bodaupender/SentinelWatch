"""Persist process status and runtime counts.

Revision ID: c9150d71fe32
Revises: 2d20f61ce1aa
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9150d71fe32"
down_revision: Union[str, None] = "2d20f61ce1aa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("process_telemetry", sa.Column("num_threads", sa.Integer(), nullable=True))
    op.add_column("process_telemetry", sa.Column("num_handles", sa.Integer(), nullable=True))
    op.add_column("process_telemetry", sa.Column("status", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("process_telemetry", "status")
    op.drop_column("process_telemetry", "num_handles")
    op.drop_column("process_telemetry", "num_threads")
