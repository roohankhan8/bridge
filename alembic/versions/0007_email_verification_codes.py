"""Track failed email verification code attempts."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_email_verification_codes"
down_revision: Union[str, None] = "0006_student_profile_drafts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "auth_tokens",
        sa.Column("failed_attempts", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("auth_tokens", "failed_attempts")
