from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import AnyHttpUrl, BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.models import StudentProfile, User
from app.db.session import get_db

router = APIRouter()


class StudentProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    full_name: str
    key_skills: list[str]
    experience_level: Literal["beginner", "intermediate", "advanced"]
    availability_hours_per_week: int
    portfolio_url: AnyHttpUrl | None


class IdentityResponse(BaseModel):
    user_id: str
    role: Literal["admin", "freelancer", "student"]
    student_profile: StudentProfileResponse | None = None


@router.get("/me", response_model=IdentityResponse)
def read_current_user(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> IdentityResponse:
    profile = db.scalar(select(StudentProfile).where(StudentProfile.user_id == user.id))
    return IdentityResponse(
        user_id=str(user.id),
        role=user.role,
        student_profile=StudentProfileResponse.model_validate(profile) if profile else None,
    )
