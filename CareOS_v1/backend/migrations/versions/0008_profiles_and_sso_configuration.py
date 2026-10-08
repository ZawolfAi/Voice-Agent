"""Add patient profile and organization SSO configuration entities."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0008_profiles_and_sso_configuration"
down_revision = "0007_auth_recovery_and_mfa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "patient_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("phone", sa.String(40)),
        sa.Column("email", sa.String(320)),
        sa.Column("address", sa.String(500)),
        sa.Column("emergency_contact", sa.String(240)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("organization_id", "patient_id", name="uq_patient_profile_org_patient"),
    )
    op.create_index("ix_patient_profiles_organization_id", "patient_profiles", ["organization_id"])
    op.create_index("ix_patient_profiles_patient_id", "patient_profiles", ["patient_id"])
    op.create_table(
        "sso_configurations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False, unique=True),
        sa.Column("provider", sa.String(24), nullable=False, server_default="oidc"),
        sa.Column("issuer_url", sa.String(500), nullable=False),
        sa.Column("client_id", sa.String(255), nullable=False),
        sa.Column("encrypted_client_secret", sa.String(500)),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_sso_configurations_organization_id", "sso_configurations", ["organization_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_sso_configurations_organization_id", table_name="sso_configurations")
    op.drop_table("sso_configurations")
    op.drop_index("ix_patient_profiles_patient_id", table_name="patient_profiles")
    op.drop_index("ix_patient_profiles_organization_id", table_name="patient_profiles")
    op.drop_table("patient_profiles")