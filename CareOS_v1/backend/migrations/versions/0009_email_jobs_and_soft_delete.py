"""Add queued email delivery and soft-delete timestamps."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009_email_jobs_and_soft_delete"
down_revision = "0008_profiles_and_sso_configuration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("users", "patients", "patient_profiles", "clinical_notes", "patient_documents", "audio_files"):
        op.add_column(table, sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
        op.create_index(f"ix_{table}_deleted_at", table, ["deleted_at"])
    op.create_table(
        "email_delivery_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("recipient", sa.String(320), nullable=False),
        sa.Column("subject", sa.String(240), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_error", sa.String(500)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_email_delivery_jobs_organization_id", "email_delivery_jobs", ["organization_id"])
    op.create_index("ix_email_delivery_jobs_recipient", "email_delivery_jobs", ["recipient"])
    op.create_index("ix_email_delivery_jobs_status", "email_delivery_jobs", ["status"])
    op.create_index("ix_email_delivery_jobs_available_at", "email_delivery_jobs", ["available_at"])


def downgrade() -> None:
    op.drop_index("ix_email_delivery_jobs_available_at", table_name="email_delivery_jobs")
    op.drop_index("ix_email_delivery_jobs_status", table_name="email_delivery_jobs")
    op.drop_index("ix_email_delivery_jobs_recipient", table_name="email_delivery_jobs")
    op.drop_index("ix_email_delivery_jobs_organization_id", table_name="email_delivery_jobs")
    op.drop_table("email_delivery_jobs")
    for table in ("audio_files", "patient_documents", "clinical_notes", "patient_profiles", "patients", "users"):
        op.drop_index(f"ix_{table}_deleted_at", table_name=table)
        op.drop_column(table, "deleted_at")
