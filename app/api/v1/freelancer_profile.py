from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, StringConstraints, UrlConstraints, model_validator
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import Settings, get_settings
from app.db.models import FreelancerProfile, User
from app.db.session import get_db

router = APIRouter(responses={401: {"description": "Missing or invalid Bridge bearer access token."}})
Skill = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Expertise = Literal[
    "Client Project Delivery",
    "Technical Mentorship & Code Review",
    "Design Sprint Facilitation",
]
ProjectDomain = Literal[
    "SaaS & Mobile Applications",
    "Brand & Design Systems",
    "E-Commerce & Web Platforms",
    "AI & Data Tools",
]
DelegationType = Literal[
    "Paid Micro-Tasks & Components",
    "1 to 3 Month Structured Internships",
    "Rapid Prototyping & User Research",
]


class FreelancerProfilePatch(BaseModel):
    full_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)] | None = None
    professional_title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=160)] | None = None
    company_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)] | None = None
    years_experience: Literal["3-5 years", "5-8 years", "8+ years", "10+ years"] | None = None
    core_skills: list[Skill] | None = Field(default=None, max_length=30)
    areas_of_expertise: list[Expertise] | None = Field(default=None, max_length=3)
    portfolio_url: Annotated[AnyHttpUrl, UrlConstraints(max_length=2048)] | None = None
    linkedin_url: Annotated[AnyHttpUrl, UrlConstraints(max_length=2048)] | None = None
    project_domains: list[ProjectDomain] | None = Field(default=None, max_length=4)
    delegation_types: list[DelegationType] | None = Field(default=None, max_length=3)
    preferred_student_skill_level: Literal["beginner", "intermediate", "advanced"] | None = None

    @model_validator(mode="after")
    def validate_lists(self):
        for field in ("core_skills", "areas_of_expertise", "project_domains", "delegation_types"):
            values = getattr(self, field)
            if field in self.model_fields_set and values is None:
                raise ValueError(f"{field} cannot be null; send an empty list to clear it")
            if values is not None and len({value.casefold() for value in values}) != len(values):
                raise ValueError(f"{field} must be unique")
        return self


class FreelancerProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    full_name: str | None = None
    professional_title: str | None = None
    company_name: str | None = None
    years_experience: str | None = None
    core_skills: list[str] = Field(default_factory=list)
    areas_of_expertise: list[str] = Field(default_factory=list)
    portfolio_url: str | None = None
    linkedin_url: str | None = None
    project_domains: list[str] = Field(default_factory=list)
    delegation_types: list[str] = Field(default_factory=list)
    preferred_student_skill_level: str | None = None
    profile_photo_url: str | None = None
    published: bool = False


def require_freelancer(user: User) -> None:
    if user.role != "freelancer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Freelancer accounts only")


def profile_response(profile: FreelancerProfile | None) -> FreelancerProfileResponse:
    if profile is None:
        return FreelancerProfileResponse()
    values = FreelancerProfileResponse.model_validate(profile).model_dump()
    values["profile_photo_url"] = "/v1/me/freelancer-profile/photo" if profile.profile_photo_name else None
    values["published"] = profile.published_at is not None
    for field in ("portfolio_url", "linkedin_url"):
        if values[field] is not None:
            values[field] = str(values[field])
    return FreelancerProfileResponse.model_validate(values)


@router.get("/me/freelancer-profile", response_model=FreelancerProfileResponse, summary="Get the freelancer onboarding profile")
def read_freelancer_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> FreelancerProfileResponse:
    require_freelancer(user)
    return profile_response(db.get(FreelancerProfile, user.id))


@router.patch("/me/freelancer-profile", response_model=FreelancerProfileResponse, summary="Save freelancer onboarding details")
def update_freelancer_profile(
    request: FreelancerProfilePatch,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FreelancerProfileResponse:
    require_freelancer(user)
    values = request.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=422, detail="At least one profile field is required")
    profile = db.get(FreelancerProfile, user.id)
    if profile is None:
        profile = FreelancerProfile(user_id=user.id)
        db.add(profile)
    for field, value in values.items():
        if field in {"portfolio_url", "linkedin_url"} and value is not None:
            value = str(value)
        setattr(profile, field, value)
    profile.published_at = None
    db.commit()
    db.refresh(profile)
    return profile_response(profile)


@router.post("/me/freelancer-profile/photo", response_model=FreelancerProfileResponse, summary="Upload a freelancer profile photo")
def upload_freelancer_photo(
    photo: Annotated[UploadFile, File(description="PNG or JPEG image, up to 5 MB.")],
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> FreelancerProfileResponse:
    require_freelancer(user)
    content = photo.file.read(5 * 1024 * 1024 + 1)
    if not content:
        raise HTTPException(status_code=422, detail="Photo cannot be empty")
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Photo must be 5 MB or smaller")
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        extension, media_type = ".png", "image/png"
    elif content.startswith(b"\xff\xd8\xff"):
        extension, media_type = ".jpg", "image/jpeg"
    else:
        raise HTTPException(status_code=415, detail="Photo must be a PNG or JPEG image")
    if photo.content_type not in {media_type, "image/jpg" if media_type == "image/jpeg" else media_type}:
        raise HTTPException(status_code=415, detail="Photo content type does not match the image")

    upload_dir = settings.profile_upload_dir / "freelancer_profiles"
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{extension}"
    destination = upload_dir / filename
    destination.write_bytes(content)
    previous_name = None
    try:
        profile = db.get(FreelancerProfile, user.id)
        if profile is None:
            profile = FreelancerProfile(user_id=user.id)
            db.add(profile)
        previous_name = profile.profile_photo_name
        profile.profile_photo_name = filename
        profile.published_at = None
        db.commit()
        db.refresh(profile)
    except Exception:
        db.rollback()
        destination.unlink(missing_ok=True)
        raise
    if previous_name:
        (upload_dir / Path(previous_name).name).unlink(missing_ok=True)
    return profile_response(profile)


@router.get("/me/freelancer-profile/photo", summary="Read the authenticated freelancer profile photo")
def read_freelancer_photo(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    require_freelancer(user)
    profile = db.get(FreelancerProfile, user.id)
    if profile is None or profile.profile_photo_name is None:
        raise HTTPException(status_code=404, detail="Profile photo not found")
    filename = Path(profile.profile_photo_name).name
    photo_path = settings.profile_upload_dir / "freelancer_profiles" / filename
    if not photo_path.is_file():
        raise HTTPException(status_code=404, detail="Profile photo not found")
    media_type = "image/png" if photo_path.suffix == ".png" else "image/jpeg"
    return FileResponse(photo_path, media_type=media_type)


@router.post("/me/freelancer-profile/publish", response_model=FreelancerProfileResponse, summary="Publish the freelancer profile")
def publish_freelancer_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> FreelancerProfileResponse:
    require_freelancer(user)
    if not user.email_verified:
        raise HTTPException(status_code=403, detail="Verify your email before publishing")
    profile = db.get(FreelancerProfile, user.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Freelancer profile not found")
    if not all((profile.full_name, profile.professional_title, profile.years_experience, profile.project_domains)):
        raise HTTPException(status_code=409, detail="Complete the required onboarding fields before publishing")
    profile.published_at = datetime.now(UTC)
    db.commit()
    db.refresh(profile)
    return profile_response(profile)
