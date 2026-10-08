"""Add FollowUp model.

Revision ID: 8ac08b6215ab
Revises: 0014_patient_codes
"""

from alembic import op
import sqlalchemy as sa


revision = "8ac08b6215ab"
down_revision = "0014_patient_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "follow_ups",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("patient_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("appointment_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("followup_type", sa.String(length=50), nullable=False, server_default="visit"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_follow_ups_organization_id"), "follow_ups", ["organization_id"], unique=False)
    op.create_index(op.f("ix_follow_ups_patient_id"), "follow_ups", ["patient_id"], unique=False)
    op.create_index(op.f("ix_follow_ups_appointment_id"), "follow_ups", ["appointment_id"], unique=False)
    op.create_index(op.f("ix_follow_ups_created_at"), "follow_ups", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_follow_ups_created_at"), table_name="follow_ups")
    op.drop_index(op.f("ix_follow_ups_appointment_id"), table_name="follow_ups")
    op.drop_index(op.f("ix_follow_ups_patient_id"), table_name="follow_ups")
    op.drop_index(op.f("ix_follow_ups_organization_id"), table_name="follow_ups")
    op.drop_table("follow_ups")
