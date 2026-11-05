"""Add local student profile photo references."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_student_profile_photos"
down_revision: Union[str, None] = "0008_freelancer_profiles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("student_profiles", sa.Column("profile_photo_name", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("student_profiles", "profile_photo_name")
