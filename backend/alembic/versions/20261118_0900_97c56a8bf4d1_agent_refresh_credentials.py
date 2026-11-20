"""Add rotating refresh credentials for agents.

Revision ID: 97c56a8bf4d1
Revises: 6f08e41d9c2b
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "97c56a8bf4d1"
down_revision: Union[str, None] = "6f08e41d9c2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_credentials",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("credential_version", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_agent_credentials"),
    )
    op.create_index("ix_agent_credentials_agent_id", "agent_credentials", ["agent_id"], unique=True)
    op.create_index("ix_agent_credentials_token_hash", "agent_credentials", ["token_hash"], unique=True)
    op.create_index("ix_agent_credentials_expires_at", "agent_credentials", ["expires_at"])
    op.create_index(
        "ix_agent_credentials_version_expiry",
        "agent_credentials",
        ["credential_version", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_credentials_version_expiry", table_name="agent_credentials")
    op.drop_index("ix_agent_credentials_expires_at", table_name="agent_credentials")
    op.drop_index("ix_agent_credentials_token_hash", table_name="agent_credentials")
    op.drop_index("ix_agent_credentials_agent_id", table_name="agent_credentials")
    op.drop_table("agent_credentials")
