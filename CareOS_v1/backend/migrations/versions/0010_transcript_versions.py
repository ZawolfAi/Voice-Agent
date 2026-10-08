"""Persist immutable clinician-edited transcript versions."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010_transcript_versions"
down_revision = "0009_email_jobs_and_soft_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "transcript_versions",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("transcript_id", uuid, sa.ForeignKey("transcripts.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("transcript_text", sa.Text(), nullable=False),
        sa.Column("editor_id", uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("transcript_id", "version", name="uq_transcript_version"),
    )
    op.create_index("ix_transcript_versions_organization_id", "transcript_versions", ["organization_id"])
    op.create_index("ix_transcript_versions_transcript_id", "transcript_versions", ["transcript_id"])
    op.create_index("ix_transcript_versions_editor_id", "transcript_versions", ["editor_id"])
    op.create_index("ix_transcript_versions_created_at", "transcript_versions", ["created_at"])


def downgrade() -> None:
    op.drop_table("transcript_versions")