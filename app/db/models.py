from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('admin', 'freelancer', 'student')", name="ck_users_role"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    role: Mapped[str] = mapped_column(String(20), default="student", server_default="student")
    email_verified: Mapped[bool] = mapped_column(default=True, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )


class StudentProfile(Base):
    __tablename__ = "student_profiles"
    __table_args__ = (
        CheckConstraint(
            "experience_level IN ('beginner', 'intermediate', 'advanced')",
            name="ck_student_profiles_experience_level",
        ),
        CheckConstraint(
            "availability_hours_per_week BETWEEN 0 AND 168",
            name="ck_student_profiles_availability",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    full_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    key_skills: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    experience_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    availability_hours_per_week: Mapped[int | None] = mapped_column(nullable=True)
    portfolio_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    university: Mapped[str | None] = mapped_column(String(200), nullable=True)
    degree_program: Mapped[str | None] = mapped_column(String(200), nullable=True)
    graduation_year: Mapped[int | None] = mapped_column(nullable=True)
    profile_photo_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    highlights: Mapped[str | None] = mapped_column(Text, nullable=True)
    digital_footprint: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    core_skills: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    supporting_skills: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    availability: Mapped[str | None] = mapped_column(String(20), nullable=True)
    preferred_work_types: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    workplace_arrangement: Mapped[str | None] = mapped_column(String(20), nullable=True)
    project_duration: Mapped[str | None] = mapped_column(String(10), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published: Mapped[bool] = mapped_column(default=False, server_default="false", nullable=False)


class AuthToken(Base):
    __tablename__ = "auth_tokens"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    purpose: Mapped[str] = mapped_column(String(20))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_attempts: Mapped[int] = mapped_column(default=0, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now())


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    family_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("budget > 0", name="ck_tasks_budget_positive"),
        CheckConstraint("status IN ('open', 'closed')", name="ck_tasks_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    budget: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    deadline: Mapped[date] = mapped_column(Date)
    required_skills: Mapped[list[str]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(10), default="open", server_default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
    )


class TaskApplication(Base):
    __tablename__ = "task_applications"
    __table_args__ = (
        UniqueConstraint("task_id", "student_id", name="uq_task_applications_task_student"),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected')", name="ck_task_applications_status"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tasks.id", ondelete="CASCADE"))
    student_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    proposal: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="pending", server_default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
    )
