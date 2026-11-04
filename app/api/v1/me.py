from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.models import StudentProfile, User
from app.db.session import get_db

router = APIRouter(responses={401: {"description": "Missing or invalid Bridge bearer access token."}})


class StudentProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    full_name: str = Field(description="Student's full name.")
    key_skills: list[str] = Field(description="Saved skill tags.")
    experience_level: Literal["beginner", "intermediate", "advanced"] = Field(description="Self-reported experience level.")
    availability_hours_per_week: int = Field(description="Available hours each week.")
    portfolio_url: AnyHttpUrl | None = Field(description="Optional portfolio URL.")


class IdentityResponse(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "user_id": "2b7fdb4a-e95d-4239-a1cf-c5d133a6ac06",
        "role": "student",
        "student_profile": {
            "full_name": "Ayesha Khan",
            "key_skills": ["Python", "FastAPI"],
            "experience_level": "intermediate",
            "availability_hours_per_week": 20,
            "portfolio_url": "https://example.com/portfolio",
        },
    }]})

    user_id: str = Field(description="Authenticated Bridge account ID.")
    role: Literal["admin", "freelancer", "student"] = Field(description="Bridge account role.")
    student_profile: StudentProfileResponse | None = Field(
        default=None, description="Present for student accounts; null otherwise."
    )


@router.get(
    "/me",
    response_model=IdentityResponse,
    summary="Get the current account",
    response_description="Authenticated account details and student profile, when present.",
)
def read_current_user(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> IdentityResponse:
    """Return the account identified by the Bridge bearer access token."""
    profile = db.scalar(select(StudentProfile).where(StudentProfile.user_id == user.id))
    return IdentityResponse(
        user_id=str(user.id),
        role=user.role,
        student_profile=StudentProfileResponse.model_validate(profile) if profile else None,
    )
