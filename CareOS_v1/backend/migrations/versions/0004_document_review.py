"""Add clinician review status to patient documents."""

from alembic import op
import sqlalchemy as sa


revision = "0004_document_review"
down_revision = "0003_document_storage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("patient_documents", sa.Column("review_status", sa.String(32), nullable=False, server_default="pending"))


def downgrade() -> None:
    op.drop_column("patient_documents", "review_status")