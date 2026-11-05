"""Add freelancer onboarding profiles."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_freelancer_profiles"
down_revision: Union[str, None] = "0007_email_verification_codes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "freelancer_profiles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=True),
        sa.Column("professional_title", sa.String(length=160), nullable=True),
        sa.Column("company_name", sa.String(length=200), nullable=True),
        sa.Column("years_experience", sa.String(length=20), nullable=True),
        sa.Column("core_skills", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("areas_of_expertise", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("portfolio_url", sa.String(length=2048), nullable=True),
        sa.Column("linkedin_url", sa.String(length=2048), nullable=True),
        sa.Column("project_domains", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("delegation_types", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("preferred_student_skill_level", sa.String(length=20), nullable=True),
        sa.Column("profile_photo_name", sa.String(length=255), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("freelancer_profiles")
