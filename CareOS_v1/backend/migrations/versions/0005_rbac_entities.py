"""Add organization-scoped roles and permissions."""

from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0005_rbac_entities"
down_revision = "0004_document_review"
branch_labels = None
depends_on = None


PERMISSIONS = (
    "users.view", "users.create", "users.update", "users.disable", "users.invite",
    "roles.view", "roles.assign", "roles.manage", "permissions.view",
    "patients.search", "patients.view", "patients.create", "patients.update",
    "appointments.view", "appointments.create", "appointments.update", "appointments.cancel",
    "encounters.create", "encounters.view", "encounters.update",
    "clinical_notes.create", "clinical_notes.view", "clinical_notes.update", "clinical_notes.approve",
    "transcripts.create", "transcripts.view", "transcripts.update", "recordings.create", "recordings.view",
    "documents.create", "documents.view", "documents.download", "documents.share_with_patient",
    "reports.view", "analytics.view", "audit_logs.view", "sso.view", "sso.manage",
    "hospital.settings.view", "hospital.settings.manage",
)


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("organization_id", "key", name="uq_role_org_key"),
    )
    op.create_index("ix_roles_organization_id", "roles", ["organization_id"])
    op.create_table(
        "permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(120), nullable=False, unique=True),
        sa.Column("description", sa.String(500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_permissions_key", "permissions", ["key"], unique=True)
    op.create_table(
        "user_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("roles.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "role_id", name="uq_user_role"),
    )
    op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"])
    op.create_index("ix_user_roles_role_id", "user_roles", ["role_id"])
    op.create_table(
        "role_permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("roles.id"), nullable=False),
        sa.Column("permission_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("permissions.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
    )
    op.create_index("ix_role_permissions_role_id", "role_permissions", ["role_id"])
    op.create_index("ix_role_permissions_permission_id", "role_permissions", ["permission_id"])

    permission_table = sa.table(
        "permissions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("key", sa.String(120)),
        sa.column("description", sa.String(500)),
    )
    op.bulk_insert(permission_table, [{"id": uuid4(), "key": key, "description": ""} for key in PERMISSIONS])


def downgrade() -> None:
    op.drop_table("role_permissions")
    op.drop_table("user_roles")
    op.drop_index("ix_permissions_key", table_name="permissions")
    op.drop_table("permissions")
    op.drop_index("ix_roles_organization_id", table_name="roles")
    op.drop_table("roles")