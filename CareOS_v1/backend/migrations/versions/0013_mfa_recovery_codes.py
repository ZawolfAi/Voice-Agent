"""Add one-time MFA recovery code hashes.

Revision ID: 0013_mfa_recovery_codes
Revises: 0012_document_encounter_link
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_mfa_recovery_codes"
down_revision = "0012_document_encounter_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("mfa_recovery_codes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "mfa_recovery_codes")