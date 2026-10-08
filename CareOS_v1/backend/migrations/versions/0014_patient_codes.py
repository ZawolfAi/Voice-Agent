"""Add stable human-readable patient codes."""

from alembic import op
import sqlalchemy as sa


revision = "0014_patient_codes"
down_revision = "0013_mfa_recovery_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("patients", sa.Column("patient_code", sa.String(length=16), nullable=True))
    bind = op.get_bind()
    patients = sa.table(
        "patients",
        sa.column("id", sa.Uuid(as_uuid=True)),
        sa.column("patient_code", sa.String(length=16)),
    )
    patient_ids = bind.execute(sa.select(patients.c.id).order_by(patients.c.id)).scalars().all()
    for sequence, patient_id in enumerate(patient_ids, start=1):
        bind.execute(
            sa.update(patients)
            .where(patients.c.id == patient_id)
            .values(patient_code=f"PAT-{sequence:012d}")
        )
    op.create_index("uq_patient_code", "patients", ["patient_code"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_patient_code", table_name="patients")
    op.drop_column("patients", "patient_code")
