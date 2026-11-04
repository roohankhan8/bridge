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

router = APIRouter(tags=["tasks"])
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
    title: TaskTitle
    description: TaskDescription
    budget: Budget
    deadline: date
    required_skills: list[Skill] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_task(self):
        validate_skills(self.required_skills)
        if self.deadline < current_utc_date():
            raise ValueError("deadline must be today or later")
        return self


class TaskUpdate(BaseModel):
    title: TaskTitle | None = None
    description: TaskDescription | None = None
    budget: Budget | None = None
    deadline: date | None = None
    required_skills: list[Skill] | None = Field(default=None, min_length=1, max_length=20)

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
    proposal: Proposal


class ApplicationDecision(BaseModel):
    status: Literal["accepted", "rejected"]


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    title: str
    description: str
    budget: Decimal
    deadline: date
    required_skills: list[str]
    status: Literal["open", "closed"]
    created_at: datetime
    updated_at: datetime


class ApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    student_id: UUID
    proposal: str
    status: Literal["pending", "accepted", "rejected"]
    created_at: datetime
    updated_at: datetime


class TaskPage(BaseModel):
    items: list[TaskResponse]
    next_cursor: UUID | None


class ApplicationPage(BaseModel):
    items: list[ApplicationResponse]
    next_cursor: UUID | None


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


@router.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(request: TaskCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
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


@router.get("/tasks", response_model=TaskPage)
def list_tasks(
    cursor: UUID | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    statement = select(Task).where(Task.status == "open", Task.deadline >= current_utc_date())
    if cursor is not None:
        statement = statement.where(Task.id > cursor)
    items = list(db.scalars(statement.order_by(Task.id).limit(limit + 1)))
    return page(items, limit, TaskPage)


@router.get("/me/tasks", response_model=TaskPage)
def list_my_tasks(
    cursor: UUID | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_role(user, "freelancer")
    statement = select(Task).where(Task.owner_id == user.id)
    if cursor is not None:
        statement = statement.where(Task.id > cursor)
    items = list(db.scalars(statement.order_by(Task.id).limit(limit + 1)))
    return page(items, limit, TaskPage)


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def read_task(task_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task = db.get(Task, task_id)
    if task is None or (
        (task.status != "open" or task.deadline < current_utc_date()) and task.owner_id != user.id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: UUID,
    request: TaskUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_role(user, "freelancer")
    task = owned_task(db, task_id, user, lock=True)
    if task.status != "open":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Closed tasks cannot be edited")
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    db.commit()
    db.refresh(task)
    return task


@router.post("/tasks/{task_id}/close", response_model=TaskResponse)
def close_task(task_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
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
)
def apply_to_task(
    task_id: UUID,
    request: ApplicationRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
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


@router.get("/tasks/{task_id}/applications", response_model=ApplicationPage)
def list_applications(
    task_id: UUID,
    cursor: UUID | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_role(user, "freelancer")
    owned_task(db, task_id, user)
    statement = select(TaskApplication).where(TaskApplication.task_id == task_id)
    if cursor is not None:
        statement = statement.where(TaskApplication.id > cursor)
    items = list(db.scalars(statement.order_by(TaskApplication.id).limit(limit + 1)))
    return page(items, limit, ApplicationPage)


@router.patch("/applications/{application_id}", response_model=ApplicationResponse)
def decide_application(
    application_id: UUID,
    request: ApplicationDecision,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
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
