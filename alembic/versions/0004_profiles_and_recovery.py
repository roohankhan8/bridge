"""Add profile fields, email verification, and recovery tokens."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_profiles_and_recovery"
down_revision: Union[str, None] = "0003_tasks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_verified", sa.Boolean(), server_default=sa.true(), nullable=False))
    for name, type_ in (
        ("university", sa.String(200)), ("degree_program", sa.String(200)), ("graduation_year", sa.Integer()),
        ("profile_photo_url", sa.String(2048)), ("highlights", sa.Text()), ("digital_footprint", sa.JSON()),
        ("core_skills", sa.JSON()), ("supporting_skills", sa.JSON()), ("availability", sa.String(20)),
        ("preferred_work_types", sa.JSON()), ("workplace_arrangement", sa.String(20)), ("project_duration", sa.String(10)),
        ("published", sa.Boolean()),
    ):
        default = "[]" if name in {"digital_footprint", "core_skills", "supporting_skills", "preferred_work_types"} else (sa.false() if name == "published" else None)
        op.add_column("student_profiles", sa.Column(name, type_, nullable=name not in {"digital_footprint", "core_skills", "supporting_skills", "preferred_work_types", "published"}, server_default=default))
    op.create_table(
        "auth_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_auth_tokens_user_id", "auth_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_auth_tokens_user_id", table_name="auth_tokens")
    op.drop_table("auth_tokens")
    for name in ("published", "project_duration", "workplace_arrangement", "preferred_work_types", "availability", "supporting_skills", "core_skills", "digital_footprint", "highlights", "profile_photo_url", "graduation_year", "degree_program", "university"):
        op.drop_column("student_profiles", name)
    op.drop_column("users", "email_verified")
