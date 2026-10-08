"""Add private storage metadata to patient documents."""

from alembic import op
import sqlalchemy as sa


revision = "0003_document_storage"
down_revision = "0002_clinical_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("patient_documents", sa.Column("storage_key", sa.String(255), nullable=True))
    op.add_column("patient_documents", sa.Column("download_url", sa.String(500), nullable=True))
    op.add_column("patient_documents", sa.Column("content_type", sa.String(80), nullable=False, server_default="application/octet-stream"))
    op.add_column("patient_documents", sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"))
    op.create_index("ix_patient_documents_storage_key", "patient_documents", ["storage_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_patient_documents_storage_key", table_name="patient_documents")
    op.drop_column("patient_documents", "size_bytes")
    op.drop_column("patient_documents", "content_type")
    op.drop_column("patient_documents", "download_url")
    op.drop_column("patient_documents", "storage_key")