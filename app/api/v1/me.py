from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, StringConstraints, UrlConstraints, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.models import StudentProfile, User
from app.api.v1.auth import CoreSkillInput
from app.db.session import get_db

router = APIRouter(responses={401: {"description": "Missing or invalid Bridge bearer access token."}})
Skill = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


class StudentProfilePatch(BaseModel):
    full_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)] | None = None
    key_skills: list[Skill] | None = Field(default=None, max_length=20)
    experience_level: Literal["beginner", "intermediate", "advanced"] | None = None
    availability_hours_per_week: int | None = Field(default=None, ge=0, le=168)
    portfolio_url: Annotated[AnyHttpUrl, UrlConstraints(max_length=2048)] | None = None
    university: str | None = Field(default=None, min_length=1, max_length=200)
    degree_program: str | None = Field(default=None, min_length=1, max_length=200)
    graduation_year: int | None = Field(default=None, ge=1950, le=2100)
    profile_photo_url: Annotated[AnyHttpUrl, UrlConstraints(max_length=2048)] | None = None
    highlights: str | None = Field(default=None, max_length=4000)
    digital_footprint: list[Annotated[AnyHttpUrl, UrlConstraints(max_length=2048)]] | None = Field(default=None, max_length=20)
    core_skills: list[CoreSkillInput] | None = Field(default=None, max_length=3)
    supporting_skills: list[Skill] | None = Field(default=None, max_length=20)
    availability: Literal["10-15", "15-20", "20-30", "full-time-40"] | None = None
    preferred_work_types: list[Literal["paid_task", "structured_internship"]] | None = Field(default=None, max_length=2)
    workplace_arrangement: Literal["remote", "hybrid"] | None = None
    project_duration: Literal["<2", "2-4", "4-12", "12+"] | None = None

    @model_validator(mode="after")
    def unique_skills(self):
        for required in ("full_name", "key_skills", "experience_level", "availability_hours_per_week"):
            if required in self.model_fields_set and getattr(self, required) is None:
                raise ValueError(f"{required} cannot be null")
        for field in ("digital_footprint", "core_skills", "supporting_skills", "preferred_work_types"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null; send an empty list to clear it")
        all_skills = (self.key_skills or []) + [s.name for s in self.core_skills or []] + (self.supporting_skills or [])
        if len({s.casefold() for s in all_skills}) != len(all_skills):
            raise ValueError("skills must be unique")
        if self.preferred_work_types is not None and len(set(self.preferred_work_types)) != len(self.preferred_work_types):
            raise ValueError("preferred_work_types must be unique")
        return self


class StudentProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    full_name: str | None = Field(default=None, description="Student's full name.")
    key_skills: list[str] = Field(default_factory=list, description="Saved skill tags.")
    experience_level: Literal["beginner", "intermediate", "advanced"] | None = Field(default=None, description="Self-reported experience level.")
    availability_hours_per_week: int | None = Field(default=None, description="Available hours each week.")
    portfolio_url: AnyHttpUrl | None = Field(description="Optional portfolio URL.")
    university: str | None = None
    degree_program: str | None = None
    graduation_year: int | None = None
    profile_photo_url: AnyHttpUrl | None = None
    highlights: str | None = None
    digital_footprint: list[AnyHttpUrl] = Field(default_factory=list)
    core_skills: list[dict] = Field(default_factory=list)
    supporting_skills: list[str] = Field(default_factory=list)
    availability: str | None = None
    preferred_work_types: list[str] = Field(default_factory=list)
    workplace_arrangement: str | None = None
    project_duration: str | None = None


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


@router.put("/me/student-profile", response_model=StudentProfileResponse, summary="Edit the student profile")
def update_student_profile(request: StudentProfilePatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> StudentProfileResponse:
    if user.role != "student":
        raise HTTPException(status_code=403, detail="Student accounts only")
    profile = db.get(StudentProfile, user.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Student profile not found")
    values = request.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=422, detail="At least one profile field is required")
    core_skills = request.core_skills if "core_skills" in values else profile.core_skills
    supporting_skills = request.supporting_skills if "supporting_skills" in values else profile.supporting_skills
    skill_names = [skill.name if isinstance(skill, CoreSkillInput) else skill["name"] for skill in core_skills]
    skill_names += supporting_skills
    if len({name.casefold() for name in skill_names}) != len(skill_names):
        raise HTTPException(status_code=422, detail="Core and supporting skills must be unique")
    for field, value in values.items():
        if field in {"portfolio_url", "profile_photo_url"}:
            value = str(value) if value else None
        elif field == "digital_footprint":
            value = [str(url) for url in value] if value is not None else None
        elif field == "core_skills":
            value = [skill.model_dump() for skill in request.core_skills] if value is not None else None
        setattr(profile, field, value)
    if "core_skills" in values or "supporting_skills" in values:
        profile.key_skills = [skill["name"] for skill in profile.core_skills] + profile.supporting_skills
    if "availability" in values:
        profile.availability_hours_per_week = {"10-15": 12, "15-20": 18, "20-30": 25, "full-time-40": 40}.get(request.availability, 0)
    profile.published_at = None
    db.commit()
    db.refresh(profile)
    return StudentProfileResponse.model_validate(profile)


@router.post("/me/student-profile/publish", response_model=StudentProfileResponse, summary="Publish the completed student profile")
def publish_student_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> StudentProfileResponse:
    if user.role != "student":
        raise HTTPException(status_code=403, detail="Student accounts only")
    if not user.email_verified:
        raise HTTPException(status_code=403, detail="Verify your email before publishing")
    profile = db.get(StudentProfile, user.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Student profile not found")
    required = (profile.full_name, profile.university, profile.degree_program, profile.graduation_year,
                profile.experience_level, profile.highlights, profile.core_skills, profile.availability,
                profile.preferred_work_types, profile.workplace_arrangement, profile.project_duration)
    if not all(required) or not profile.profile_photo_url or not profile.core_skills:
        raise HTTPException(status_code=409, detail="Complete all profile steps before publishing")
    profile.published_at = datetime.now(UTC)
    db.commit()
    db.refresh(profile)
    return StudentProfileResponse.model_validate(profile)


@router.get("/students/{user_id}/profile", response_model=StudentProfileResponse, summary="View the public student profile")
def read_public_student_profile(user_id: UUID, db: Session = Depends(get_db)) -> StudentProfileResponse:
    profile = db.scalar(select(StudentProfile).join(User).where(
        StudentProfile.user_id == user_id,
        StudentProfile.published_at.is_not(None),
        User.email_verified.is_(True),
    ))
    if profile is None:
        raise HTTPException(status_code=404, detail="Student profile not found")
    return StudentProfileResponse.model_validate(profile)
