"""Preserve optional Windows service runtime metadata.

Revision ID: 2d20f61ce1aa
Revises: 97c56a8bf4d1
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2d20f61ce1aa"
down_revision: Union[str, None] = "97c56a8bf4d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("service_telemetry", sa.Column("description", sa.String(length=1024), nullable=True))
    op.add_column("service_telemetry", sa.Column("pid", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("service_telemetry", "pid")
    op.drop_column("service_telemetry", "description")
