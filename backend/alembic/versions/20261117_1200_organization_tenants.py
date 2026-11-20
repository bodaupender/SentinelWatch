"""Add organization tenant foundations and backfill legacy rows safely."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import uuid

revision: str = "6f08e41d9c2b"
down_revision: Union[str, None] = "88fde11c46c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEGACY_ORGANIZATION_ID = "00000000-0000-4000-8000-000000000001"


def upgrade() -> None:
    bind = op.get_bind()
    organization_status = sa.Enum("active", "suspended", name="organizationstatus", create_constraint=True)
    membership_role = sa.Enum("owner", "admin", "analyst", "viewer", name="organizationrole", create_constraint=True)

    op.create_table(
        "organizations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("status", organization_status, nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)
    op.create_index("ix_organizations_status", "organizations", ["status"])

    op.create_table(
        "organization_memberships",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", membership_role, nullable=False, server_default="viewer"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_membership_org_user"),
    )
    op.create_index("ix_organization_memberships_organization_id", "organization_memberships", ["organization_id"])
    op.create_index("ix_organization_memberships_user_id", "organization_memberships", ["user_id"])
    op.create_index("ix_membership_user_org", "organization_memberships", ["user_id", "organization_id"])

    op.execute(
        sa.text(
            "INSERT INTO organizations (id, name, slug, status, created_at, updated_at) "
            "VALUES (:id, :name, :slug, :status, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ).bindparams(id=LEGACY_ORGANIZATION_ID, name="Legacy Organization", slug="legacy", status="active")
    )
    op.add_column(
        "audit_log",
        sa.Column("organization_id", sa.String(36), nullable=False, server_default=LEGACY_ORGANIZATION_ID),
    )
    with op.batch_alter_table("audit_log") as batch:
        batch.create_foreign_key(
            "fk_audit_log_organization_id_organizations", "organizations",
            ["organization_id"], ["id"], ondelete="RESTRICT",
        )
        batch.alter_column("organization_id", existing_type=sa.String(36), server_default=None)
    op.create_index("ix_audit_log_organization_id", "audit_log", ["organization_id"])

    op.add_column(
        "rules",
        sa.Column("organization_id", sa.String(36), nullable=False, server_default=LEGACY_ORGANIZATION_ID),
    )
    op.drop_index("ix_rules_name", table_name="rules")
    with op.batch_alter_table("rules") as batch:
        batch.create_foreign_key(
            "fk_rules_organization_id_organizations", "organizations",
            ["organization_id"], ["id"], ondelete="CASCADE",
        )
        batch.alter_column("organization_id", existing_type=sa.String(36), server_default=None)
    op.create_index("ix_rules_organization_id", "rules", ["organization_id"])
    op.create_index("ix_rules_name", "rules", ["name"])
    op.create_index("uq_rules_organization_name", "rules", ["organization_id", "name"], unique=True)

    op.add_column(
        "suppression_rules",
        sa.Column("organization_id", sa.String(36), nullable=False, server_default=LEGACY_ORGANIZATION_ID),
    )
    with op.batch_alter_table("suppression_rules") as batch:
        batch.create_foreign_key(
            "fk_suppression_rules_organization_id_organizations", "organizations",
            ["organization_id"], ["id"], ondelete="CASCADE",
        )
        batch.alter_column("organization_id", existing_type=sa.String(36), server_default=None)
    op.create_index("ix_suppression_rules_organization_id", "suppression_rules", ["organization_id"])

    op.add_column("agents", sa.Column("organization_id", sa.String(36), nullable=True))
    op.create_index("ix_agents_organization_id", "agents", ["organization_id"])
    op.add_column("agents", sa.Column("credential_version", sa.Integer(), nullable=False, server_default="0"))
    with op.batch_alter_table("agents") as batch:
        batch.alter_column("credential_version", existing_type=sa.Integer(), server_default=None)
    with op.batch_alter_table("agents") as batch:
        batch.create_foreign_key(
            "fk_agents_organization_id_organizations", "organizations",
            ["organization_id"], ["id"], ondelete="RESTRICT",
        )
    op.add_column("enrollment_tokens", sa.Column("organization_id", sa.String(36), nullable=True))
    op.create_index("ix_enrollment_tokens_organization_id", "enrollment_tokens", ["organization_id"])
    with op.batch_alter_table("enrollment_tokens") as batch:
        batch.create_foreign_key(
            "fk_enrollment_tokens_organization_id_organizations", "organizations",
            ["organization_id"], ["id"], ondelete="CASCADE",
        )

    # Preserve every legacy user's and endpoint's access by assigning the existing rows to one
    # explicit tenant. Subsequent onboarding creates isolated organizations.
    op.execute(
        sa.text("UPDATE agents SET organization_id = :organization_id").bindparams(
            organization_id=LEGACY_ORGANIZATION_ID
        )
    )
    op.execute(
        sa.text("UPDATE enrollment_tokens SET organization_id = :organization_id").bindparams(
            organization_id=LEGACY_ORGANIZATION_ID
        )
    )
    with op.batch_alter_table("agents") as batch:
        batch.alter_column("organization_id", existing_type=sa.String(36), nullable=False)
    with op.batch_alter_table("enrollment_tokens") as batch:
        batch.alter_column("organization_id", existing_type=sa.String(36), nullable=False)
    users = bind.execute(sa.text("SELECT id, role FROM users")).mappings().all()
    for user in users:
        raw_role = user["role"]
        legacy_role = str(getattr(raw_role, "value", raw_role)).rsplit(".", 1)[-1].lower()
        role = "owner" if legacy_role == "admin" else legacy_role
        if role not in {"owner", "admin", "analyst", "viewer"}:
            role = "viewer"
        bind.execute(
            sa.text(
                "INSERT INTO organization_memberships (id, organization_id, user_id, role, created_at) "
                "VALUES (:id, :organization_id, :user_id, :role, CURRENT_TIMESTAMP)"
            ),
            {
                "id": str(uuid.uuid4()),
                "organization_id": LEGACY_ORGANIZATION_ID,
                "user_id": user["id"],
                "role": role,
            },
        )


def downgrade() -> None:
    # Keep tenant records and existing telemetry. Remove only tenant metadata added here.
    op.drop_index("ix_suppression_rules_organization_id", table_name="suppression_rules")
    with op.batch_alter_table("suppression_rules") as batch:
        batch.drop_constraint("fk_suppression_rules_organization_id_organizations", type_="foreignkey")
        batch.drop_column("organization_id")
    op.drop_index("uq_rules_organization_name", table_name="rules")
    op.drop_index("ix_rules_name", table_name="rules")
    op.drop_index("ix_rules_organization_id", table_name="rules")
    with op.batch_alter_table("rules") as batch:
        batch.drop_constraint("fk_rules_organization_id_organizations", type_="foreignkey")
        batch.drop_column("organization_id")
    op.drop_index("ix_audit_log_organization_id", table_name="audit_log")
    with op.batch_alter_table("audit_log") as batch:
        batch.drop_constraint("fk_audit_log_organization_id_organizations", type_="foreignkey")
        batch.drop_column("organization_id")
    with op.batch_alter_table("enrollment_tokens") as batch:
        batch.drop_constraint("fk_enrollment_tokens_organization_id_organizations", type_="foreignkey")
    op.drop_index("ix_enrollment_tokens_organization_id", table_name="enrollment_tokens")
    op.drop_column("enrollment_tokens", "organization_id")
    with op.batch_alter_table("agents") as batch:
        batch.drop_constraint("fk_agents_organization_id_organizations", type_="foreignkey")
    op.drop_index("ix_agents_organization_id", table_name="agents")
    op.drop_column("agents", "credential_version")
    op.drop_column("agents", "organization_id")
    op.drop_index("ix_membership_user_org", table_name="organization_memberships")
    op.drop_index("ix_organization_memberships_user_id", table_name="organization_memberships")
    op.drop_index("ix_organization_memberships_organization_id", table_name="organization_memberships")
    op.drop_table("organization_memberships")
    op.drop_index("ix_organizations_status", table_name="organizations")
    op.drop_index("ix_organizations_slug", table_name="organizations")
    op.drop_table("organizations")
