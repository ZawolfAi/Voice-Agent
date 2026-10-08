"""Add durable asynchronous transcription jobs."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011_transcription_jobs"
down_revision = "0010_transcript_versions"
branch_labels = None
depends_on = None

def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table("transcription_jobs",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("audio_file_id", uuid, sa.ForeignKey("audio_files.id"), nullable=False),
        sa.Column("transcript_id", uuid, sa.ForeignKey("transcripts.id"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="QUEUED"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_error", sa.String(120)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("audio_file_id", name="uq_transcription_job_audio"),
    )
    for column in ("organization_id", "audio_file_id", "transcript_id", "status", "available_at", "created_at"):
        op.create_index(f"ix_transcription_jobs_{column}", "transcription_jobs", [column])

def downgrade() -> None:
    op.drop_table("transcription_jobs")