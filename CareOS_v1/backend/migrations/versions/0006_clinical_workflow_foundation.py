"""Add encounters, audio, transcripts, immutable note versions, and invite lifecycle fields."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0006_clinical_workflow_foundation"
down_revision = "0005_rbac_entities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("team_invites", sa.Column("token_hash", sa.String(128), nullable=True))
    op.add_column("team_invites", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("team_invites", sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_team_invites_token_hash", "team_invites", ["token_hash"], unique=True)
    op.create_table(
        "encounters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("clinician_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("encounter_type", sa.String(40), nullable=False, server_default="consultation"),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    for name, table, columns in [
        ("ix_encounters_organization_id", "encounters", ["organization_id"]),
        ("ix_encounters_patient_id", "encounters", ["patient_id"]),
        ("ix_encounters_clinician_id", "encounters", ["clinician_id"]),
        ("ix_encounters_created_at", "encounters", ["created_at"]),
    ]:
        op.create_index(name, table, columns)
    op.add_column("clinical_notes", sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounters.id"), nullable=True))
    op.create_index("ix_clinical_notes_encounter_id", "clinical_notes", ["encounter_id"])
    op.create_table(
        "clinical_note_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("clinical_note_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinical_notes.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("ai_draft", sa.Text()),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("clinical_note_id", "version", name="uq_clinical_note_version"),
    )
    op.create_index("ix_clinical_note_versions_organization_id", "clinical_note_versions", ["organization_id"])
    op.create_index("ix_clinical_note_versions_clinical_note_id", "clinical_note_versions", ["clinical_note_id"])
    op.create_index("ix_clinical_note_versions_author_id", "clinical_note_versions", ["author_id"])
    op.create_index("ix_clinical_note_versions_created_at", "clinical_note_versions", ["created_at"])
    op.create_table(
        "audio_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounters.id"), nullable=False),
        sa.Column("storage_key", sa.String(255), nullable=False, unique=True),
        sa.Column("content_type", sa.String(80), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retention_status", sa.String(32), nullable=False, server_default="RETAINED"),
        sa.Column("delete_after", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audio_files_organization_id", "audio_files", ["organization_id"])
    op.create_index("ix_audio_files_patient_id", "audio_files", ["patient_id"])
    op.create_index("ix_audio_files_encounter_id", "audio_files", ["encounter_id"])
    op.create_index("ix_audio_files_storage_key", "audio_files", ["storage_key"], unique=True)
    op.create_index("ix_audio_files_created_at", "audio_files", ["created_at"])
    op.create_table(
        "transcripts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounters.id"), nullable=False),
        sa.Column("audio_file_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("audio_files.id"), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("language", sa.String(16), nullable=False, server_default="ar-EG"),
        sa.Column("dialect", sa.String(40), nullable=False, server_default="egyptian_arabic"),
        sa.Column("transcript_text", sa.Text()),
        sa.Column("status", sa.String(24), nullable=False, server_default="UPLOADING"),
        sa.Column("confidence", sa.Float()),
        sa.Column("error_code", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    for name, columns in [("organization_id", ["organization_id"]), ("patient_id", ["patient_id"]), ("encounter_id", ["encounter_id"]), ("audio_file_id", ["audio_file_id"]), ("created_at", ["created_at"])]:
        op.create_index(f"ix_transcripts_{name}", "transcripts", columns)


def downgrade() -> None:
    op.drop_table("transcripts")
    op.drop_table("audio_files")
    op.drop_table("clinical_note_versions")
    op.drop_index("ix_clinical_notes_encounter_id", table_name="clinical_notes")
    op.drop_column("clinical_notes", "encounter_id")
    for name in ["ix_encounters_created_at", "ix_encounters_clinician_id", "ix_encounters_patient_id", "ix_encounters_organization_id"]:
        op.drop_index(name, table_name="encounters")
    op.drop_table("encounters")
    op.drop_index("ix_team_invites_token_hash", table_name="team_invites")
    op.drop_column("team_invites", "accepted_at")
    op.drop_column("team_invites", "expires_at")
    op.drop_column("team_invites", "token_hash")