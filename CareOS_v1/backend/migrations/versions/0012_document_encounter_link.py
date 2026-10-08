"""Link generated patient documents to encounters."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0012_document_encounter_link"
down_revision = "0011_transcription_jobs"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("patient_documents", sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounters.id"), nullable=True))
    op.create_index("ix_patient_documents_encounter_id", "patient_documents", ["encounter_id"])

def downgrade() -> None:
    op.drop_index("ix_patient_documents_encounter_id", table_name="patient_documents")
    op.drop_column("patient_documents", "encounter_id")