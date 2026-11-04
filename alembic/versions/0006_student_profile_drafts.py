"""Allow student profiles to be saved as step-by-step drafts."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_student_profile_drafts"
down_revision: Union[str, None] = "0005_profile_publication"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("student_profiles") as batch_op:
        batch_op.alter_column("full_name", existing_type=sa.String(120), nullable=True)
        batch_op.alter_column("key_skills", existing_type=sa.JSON(), nullable=True)
        batch_op.alter_column("experience_level", existing_type=sa.String(20), nullable=True)
        batch_op.alter_column("availability_hours_per_week", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    connection = op.get_bind()
    incomplete = connection.execute(sa.text(
        "SELECT count(*) FROM student_profiles WHERE full_name IS NULL "
        "OR key_skills IS NULL OR experience_level IS NULL "
        "OR availability_hours_per_week IS NULL"
    )).scalar_one()
    if incomplete:
        raise RuntimeError("Cannot downgrade while student profile drafts are incomplete")
    with op.batch_alter_table("student_profiles") as batch_op:
        batch_op.alter_column("full_name", existing_type=sa.String(120), nullable=False)
        batch_op.alter_column("key_skills", existing_type=sa.JSON(), nullable=False)
        batch_op.alter_column("experience_level", existing_type=sa.String(20), nullable=False)
        batch_op.alter_column("availability_hours_per_week", existing_type=sa.Integer(), nullable=False)
