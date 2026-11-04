"""Track explicit publication of complete student profiles."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_profile_publication"
down_revision: Union[str, None] = "0004_profiles_and_recovery"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("student_profiles", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("student_profiles", "published_at")
