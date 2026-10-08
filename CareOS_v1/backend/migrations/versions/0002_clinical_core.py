"""create clinical core tables and handoff integration queue tables"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_clinical_core"
down_revision = "0001_identity_and_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table("patients",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("medical_record_number", sa.String(64), nullable=False),
        sa.Column("given_name", sa.String(120), nullable=False), sa.Column("family_name", sa.String(120), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=False), sa.Column("gender", sa.String(24), nullable=False, server_default="unspecified"),
        sa.Column("condition", sa.String(240), nullable=False, server_default=""), sa.Column("care_status", sa.String(40), nullable=False, server_default="stable"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "medical_record_number", name="uq_patient_org_mrn"))
    op.create_index("ix_patients_organization_id", "patients", ["organization_id"])
    op.create_table("appointments",
        sa.Column("id", uuid, primary_key=True), sa.Column("organization_id", uuid, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("patient_id", uuid, sa.ForeignKey("patients.id"), nullable=False), sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"), sa.Column("reason", sa.String(240), nullable=False),
        sa.Column("reminder_status", sa.String(32), nullable=False, server_default="not_scheduled"), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_appointments_organization_id", "appointments", ["organization_id"]); op.create_index("ix_appointments_patient_id", "appointments", ["patient_id"]); op.create_index("ix_appointments_starts_at", "appointments", ["starts_at"])
    op.create_table("clinical_notes",
        sa.Column("id", uuid, primary_key=True), sa.Column("organization_id", uuid, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("patient_id", uuid, sa.ForeignKey("patients.id"), nullable=False), sa.Column("author_id", uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("body", sa.Text(), nullable=False), sa.Column("ai_draft", sa.Text()), sa.Column("status", sa.String(24), nullable=False, server_default="draft"), sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("signed_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_clinical_notes_organization_id", "clinical_notes", ["organization_id"]); op.create_index("ix_clinical_notes_patient_id", "clinical_notes", ["patient_id"])
    op.create_table("patient_documents",
        sa.Column("id", uuid, primary_key=True), sa.Column("organization_id", uuid, sa.ForeignKey("organizations.id"), nullable=False), sa.Column("patient_id", uuid, sa.ForeignKey("patients.id"), nullable=False), sa.Column("filename", sa.String(255), nullable=False), sa.Column("ocr_status", sa.String(32), nullable=False, server_default="queued"), sa.Column("extracted_text", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_patient_documents_organization_id", "patient_documents", ["organization_id"]); op.create_index("ix_patient_documents_patient_id", "patient_documents", ["patient_id"])
    op.create_table("reminder_jobs",
        sa.Column("id", uuid, primary_key=True), sa.Column("organization_id", uuid, sa.ForeignKey("organizations.id"), nullable=False), sa.Column("appointment_id", uuid, sa.ForeignKey("appointments.id"), nullable=False), sa.Column("channel", sa.String(24), nullable=False, server_default="sandbox"), sa.Column("status", sa.String(32), nullable=False, server_default="queued"), sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_reminder_jobs_organization_id", "reminder_jobs", ["organization_id"]); op.create_index("ix_reminder_jobs_appointment_id", "reminder_jobs", ["appointment_id"])


def downgrade() -> None:
    for table in ("reminder_jobs", "patient_documents", "clinical_notes", "appointments", "patients"):
        op.drop_table(table)
