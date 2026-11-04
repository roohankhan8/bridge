from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.models import Task, TaskApplication, User
from app.db.session import get_db

router = APIRouter(
    tags=["tasks"],
    responses={
        401: {"description": "Missing or invalid Bridge bearer access token."},
        422: {"description": "A request field or query parameter failed validation."},
    },
)
TaskTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)]
TaskDescription = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]
Skill = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Proposal = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]
Budget = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]


def current_utc_date() -> date:
    return datetime.now(UTC).date()


def validate_skills(skills: list[str]) -> list[str]:
    if len({skill.casefold() for skill in skills}) != len(skills):
        raise ValueError("required_skills must be unique")
    return skills


class TaskCreate(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "title": "Build a student dashboard",
        "description": "Create a responsive dashboard for student project tracking.",
        "budget": "25000.00",
        "deadline": "2026-12-31",
        "required_skills": ["FastAPI", "PostgreSQL"],
    }]})

    title: TaskTitle = Field(description="Task title (2–200 characters).", examples=["Build a student dashboard"])
    description: TaskDescription = Field(description="Task scope and deliverables (1–10,000 characters).")
    budget: Budget = Field(description="Positive budget in PKR, with up to two decimal places.", examples=["25000.00"])
    deadline: date = Field(description="Last calendar date to apply, in YYYY-MM-DD format.", examples=["2026-12-31"])
    required_skills: list[Skill] = Field(
        min_length=1,
        max_length=20,
        description="1–20 unique skill tags; each is 1–60 characters.",
        examples=[["FastAPI", "PostgreSQL"]],
    )

    @model_validator(mode="after")
    def validate_task(self):
        validate_skills(self.required_skills)
        if self.deadline < current_utc_date():
            raise ValueError("deadline must be today or later")
        return self


class TaskUpdate(BaseModel):
    title: TaskTitle | None = Field(default=None, description="Replacement title (2–200 characters).")
    description: TaskDescription | None = Field(default=None, description="Replacement description (1–10,000 characters).")
    budget: Budget | None = Field(default=None, description="Replacement positive budget in PKR, up to two decimal places.")
    deadline: date | None = Field(default=None, description="Replacement deadline date (YYYY-MM-DD), today or later in UTC.")
    required_skills: list[Skill] | None = Field(
        default=None,
        min_length=1,
        max_length=20,
        description="Replacement list of 1–20 unique skill tags, each 1–60 characters.",
    )

    @model_validator(mode="after")
    def validate_changes(self):
        if not self.model_fields_set or any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("provide non-null task fields to update")
        if self.required_skills is not None:
            validate_skills(self.required_skills)
        if self.deadline is not None and self.deadline < current_utc_date():
            raise ValueError("deadline must be today or later")
        return self


class ApplicationRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "proposal": "I have built similar FastAPI services and can deliver the dashboard in two weeks.",
    }]})

    proposal: Proposal = Field(description="Proposal text (1–5,000 characters).")


class ApplicationDecision(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"status": "accepted"}]})

    status: Literal["accepted", "rejected"] = Field(description="Final decision for a pending application.")


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, json_schema_extra={"examples": [{
        "id": "9dd5d6d6-89ae-4d10-9cf4-4ccb06d785d9",
        "owner_id": "e88d05b8-bb5a-4b2c-9e48-1b926ba88a71",
        "title": "Build a student dashboard",
        "description": "Create a responsive dashboard for student project tracking.",
        "budget": "25000.00",
        "deadline": "2026-12-31",
        "required_skills": ["FastAPI", "PostgreSQL"],
        "status": "open",
        "created_at": "2026-11-05T12:00:00Z",
        "updated_at": "2026-11-05T12:00:00Z",
    }]})

    id: UUID = Field(description="Task identifier.")
    owner_id: UUID = Field(description="Freelancer account that owns the task.")
    title: str = Field(description="Task title.")
    description: str = Field(description="Task scope and deliverables.")
    budget: Decimal = Field(description="Task budget in PKR.")
    deadline: date = Field(description="Last date to apply (YYYY-MM-DD, UTC calendar date).")
    required_skills: list[str] = Field(description="Required skill tags.")
    status: Literal["open", "closed"] = Field(description="Closed tasks do not accept applications.")
    created_at: datetime = Field(description="Creation timestamp in UTC.")
    updated_at: datetime = Field(description="Last update timestamp in UTC.")


class ApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, json_schema_extra={"examples": [{
        "id": "4caeaeb8-6fb9-420f-bf78-f49c7befed9b",
        "task_id": "9dd5d6d6-89ae-4d10-9cf4-4ccb06d785d9",
        "student_id": "2b7fdb4a-e95d-4239-a1cf-c5d133a6ac06",
        "proposal": "I have built similar FastAPI services and can deliver the dashboard in two weeks.",
        "status": "pending",
        "created_at": "2026-11-05T12:00:00Z",
        "updated_at": "2026-11-05T12:00:00Z",
    }]})

    id: UUID = Field(description="Application identifier.")
    task_id: UUID = Field(description="Task being applied to.")
    student_id: UUID = Field(description="Student account that submitted the proposal.")
    proposal: str = Field(description="Student's proposal.")
    status: Literal["pending", "accepted", "rejected"] = Field(description="Current application decision.")
    created_at: datetime = Field(description="Submission timestamp in UTC.")
    updated_at: datetime = Field(description="Last update timestamp in UTC.")


class TaskPage(BaseModel):
    """Cursor-paginated task collection; pass next_cursor as cursor to fetch more."""

    items: list[TaskResponse] = Field(description="Tasks in this page.")
    next_cursor: UUID | None = Field(description="Pass this task ID as `cursor` to fetch the next page; null when complete.")


class ApplicationPage(BaseModel):
    """Cursor-paginated application collection; pass next_cursor as cursor to fetch more."""

    items: list[ApplicationResponse] = Field(description="Applications in this page.")
    next_cursor: UUID | None = Field(description="Pass this application ID as `cursor` to fetch the next page; null when complete.")


def require_role(user: User, role: str) -> None:
    if user.role != role:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted")


def owned_task(db: Session, task_id: UUID, user: User, *, lock: bool = False) -> Task:
    statement = select(Task).where(Task.id == task_id)
    if lock:
        statement = statement.with_for_update()
    task = db.scalar(statement)
    if task is None or task.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


def page(items: list, limit: int, response_type: type[TaskPage] | type[ApplicationPage]):
    has_more = len(items) > limit
    visible_items = items[:limit]
    return response_type(
        items=visible_items,
        next_cursor=visible_items[-1].id if has_more else None,
    )


@router.post(
    "/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a task",
    responses={403: {"description": "Only freelancers can create tasks."}},
)
def create_task(request: TaskCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Create an open task. The authenticated freelancer becomes its owner."""
    require_role(user, "freelancer")
    task = Task(
        owner_id=user.id,
        title=request.title,
        description=request.description,
        budget=request.budget,
        deadline=request.deadline,
        required_skills=request.required_skills,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.get(
    "/tasks",
    response_model=TaskPage,
    summary="Browse open tasks",
    response_description="Open tasks whose deadline is today or later (UTC).",
)
def list_tasks(
    cursor: UUID | None = Query(default=None, description="Last task ID from the previous page."),
    limit: int = Query(default=20, ge=1, le=100, description="Number of tasks to return (1–100)."),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Browse tasks with UUID keyset pagination; use next_cursor for the next page."""
    statement = select(Task).where(Task.status == "open", Task.deadline >= current_utc_date())
    if cursor is not None:
        statement = statement.where(Task.id > cursor)
    items = list(db.scalars(statement.order_by(Task.id).limit(limit + 1)))
    return page(items, limit, TaskPage)


@router.get(
    "/me/tasks",
    response_model=TaskPage,
    summary="List my tasks",
    responses={403: {"description": "Only freelancers can list their tasks."}},
)
def list_my_tasks(
    cursor: UUID | None = Query(default=None, description="Last task ID from the previous page."),
    limit: int = Query(default=20, ge=1, le=100, description="Number of tasks to return (1–100)."),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List the authenticated freelancer's open and closed tasks."""
    require_role(user, "freelancer")
    statement = select(Task).where(Task.owner_id == user.id)
    if cursor is not None:
        statement = statement.where(Task.id > cursor)
    items = list(db.scalars(statement.order_by(Task.id).limit(limit + 1)))
    return page(items, limit, TaskPage)


@router.get(
    "/tasks/{task_id}",
    response_model=TaskResponse,
    summary="Get task details",
    responses={404: {"description": "Task is missing or not visible to this user."}},
)
def read_task(task_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Read an open task; its owner can also read it after closing or expiry."""
    task = db.get(Task, task_id)
    if task is None or (
        (task.status != "open" or task.deadline < current_utc_date()) and task.owner_id != user.id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.patch(
    "/tasks/{task_id}",
    response_model=TaskResponse,
    summary="Edit an open task",
    responses={403: {"description": "Only freelancers can edit tasks."}, 404: {"description": "Task not found or not owned by caller."}, 409: {"description": "Closed tasks cannot be edited."}},
)
def update_task(
    task_id: UUID,
    request: TaskUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Partially update an open task owned by the authenticated freelancer."""
    require_role(user, "freelancer")
    task = owned_task(db, task_id, user, lock=True)
    if task.status != "open":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Closed tasks cannot be edited")
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    db.commit()
    db.refresh(task)
    return task


@router.post(
    "/tasks/{task_id}/close",
    response_model=TaskResponse,
    summary="Close a task",
    responses={403: {"description": "Only freelancers can close tasks."}, 404: {"description": "Task not found or not owned by caller."}},
)
def close_task(task_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Permanently close an owned task and stop accepting applications."""
    require_role(user, "freelancer")
    task = owned_task(db, task_id, user, lock=True)
    if task.status != "closed":
        task.status = "closed"
        db.commit()
        db.refresh(task)
    return task


@router.post(
    "/tasks/{task_id}/applications",
    response_model=ApplicationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Apply to a task",
    responses={403: {"description": "Only students can apply."}, 404: {"description": "Task not found."}, 409: {"description": "Task is closed/expired, is owned by caller, or caller already applied."}},
)
def apply_to_task(
    task_id: UUID,
    request: ApplicationRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Submit one proposal to an open task before its UTC deadline date ends."""
    require_role(user, "student")
    task = db.scalar(select(Task).where(Task.id == task_id).with_for_update())
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if task.owner_id == user.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot apply to your own task")
    if task.status != "open" or task.deadline < current_utc_date():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Task is not accepting applications")
    application = TaskApplication(task_id=task.id, student_id=user.id, proposal=request.proposal)
    db.add(application)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already applied to this task") from exc
    db.refresh(application)
    return application


@router.get(
    "/tasks/{task_id}/applications",
    response_model=ApplicationPage,
    summary="List task applications",
    responses={403: {"description": "Only freelancers can review applications."}, 404: {"description": "Task not found or not owned by caller."}},
)
def list_applications(
    task_id: UUID,
    cursor: UUID | None = Query(default=None, description="Last application ID from the previous page."),
    limit: int = Query(default=20, ge=1, le=100, description="Number of applications to return (1–100)."),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List applications for a task owned by the authenticated freelancer."""
    require_role(user, "freelancer")
    owned_task(db, task_id, user)
    statement = select(TaskApplication).where(TaskApplication.task_id == task_id)
    if cursor is not None:
        statement = statement.where(TaskApplication.id > cursor)
    items = list(db.scalars(statement.order_by(TaskApplication.id).limit(limit + 1)))
    return page(items, limit, ApplicationPage)


@router.patch(
    "/applications/{application_id}",
    response_model=ApplicationResponse,
    summary="Decide an application",
    responses={403: {"description": "Only freelancers can decide applications."}, 404: {"description": "Application or owned task not found."}, 409: {"description": "Application already has a different decision."}},
)
def decide_application(
    application_id: UUID,
    request: ApplicationDecision,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Accept or reject a pending application; repeating the same decision is safe."""
    require_role(user, "freelancer")
    application = db.get(TaskApplication, application_id)
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    owned_task(db, application.task_id, user)
    if application.status != "pending":
        if application.status == request.status:
            return application
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Application already decided")
    result = db.execute(
        update(TaskApplication)
        .where(TaskApplication.id == application.id, TaskApplication.status == "pending")
        .values(status=request.status, updated_at=datetime.now(UTC))
    )
    if result.rowcount != 1:
        db.rollback()
        application = db.get(TaskApplication, application_id)
        if application is not None and application.status == request.status:
            return application
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Application already decided")
    db.commit()
    db.refresh(application)
    return application
