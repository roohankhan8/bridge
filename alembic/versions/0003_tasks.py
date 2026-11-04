"""Add tasks and applications."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_tasks"
down_revision: Union[str, None] = "0002_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("budget", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("deadline", sa.Date(), nullable=False),
        sa.Column("required_skills", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=10), server_default="open", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("budget > 0", name="ck_tasks_budget_positive"),
        sa.CheckConstraint("status IN ('open', 'closed')", name="ck_tasks_status"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tasks_owner_id", "tasks", ["owner_id"])
    op.create_index("ix_tasks_status", "tasks", ["status"])
    op.create_table(
        "task_applications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("proposal", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=10), server_default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected')", name="ck_task_applications_status"
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "student_id", name="uq_task_applications_task_student"),
    )
    op.create_index("ix_task_applications_student_id", "task_applications", ["student_id"])


def downgrade() -> None:
    op.drop_index("ix_task_applications_student_id", table_name="task_applications")
    op.drop_table("task_applications")
    op.drop_index("ix_tasks_status", table_name="tasks")
    op.drop_index("ix_tasks_owner_id", table_name="tasks")
    op.drop_table("tasks")
