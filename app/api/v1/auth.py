from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from google.auth import exceptions as google_exceptions
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token as google_id_token
from pydantic import AnyHttpUrl, BaseModel, EmailStr, Field, StringConstraints, UrlConstraints, model_validator
from pwdlib import PasswordHash
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import hash_refresh_token, issue_tokens, signing_secret
from app.core.config import Settings, get_settings
from app.db.models import RefreshSession, StudentProfile, User
from app.db.session import get_db

router = APIRouter(prefix="/auth", tags=["authentication"])
password_hasher = PasswordHash.recommended()
dummy_password_hash = password_hasher.hash("bridge-invalid-login-placeholder")
RoleChoice = Literal["student", "freelancer"]
Skill = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


class StudentProfileInput(BaseModel):
    full_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
    key_skills: list[Skill] = Field(min_length=1, max_length=20)
    experience_level: Literal["beginner", "intermediate", "advanced"]
    availability_hours_per_week: int = Field(ge=0, le=168)
    portfolio_url: Annotated[AnyHttpUrl, UrlConstraints(max_length=2048)] | None = None

    @model_validator(mode="after")
    def skills_are_unique(self):
        if len({skill.casefold() for skill in self.key_skills}) != len(self.key_skills):
            raise ValueError("key_skills must be unique")
        return self


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: RoleChoice = "student"
    student_profile: StudentProfileInput | None = None

    @model_validator(mode="after")
    def require_student_profile(self):
        if self.role == "student" and self.student_profile is None:
            raise ValueError("student_profile is required for student accounts")
        if self.role == "freelancer" and self.student_profile is not None:
            raise ValueError("student_profile is only valid for student accounts")
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class GoogleSignInRequest(BaseModel):
    id_token: str = Field(min_length=1, max_length=8192)
    role: RoleChoice = "student"
    student_profile: StudentProfileInput | None = None


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=512)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def add_student_profile(db: Session, user: User, profile: StudentProfileInput | None) -> None:
    if profile is not None:
        db.add(
            StudentProfile(
                user_id=user.id,
                full_name=profile.full_name,
                key_skills=profile.key_skills,
                experience_level=profile.experience_level,
                availability_hours_per_week=profile.availability_hours_per_week,
                portfolio_url=str(profile.portfolio_url) if profile.portfolio_url else None,
            )
        )


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def configured_google_audiences(settings: Settings) -> list[str]:
    audiences = [value.strip() for value in settings.google_client_ids if value.strip()]
    if not audiences:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is not configured",
        )
    return audiences


def verify_google_token(token: str, settings: Settings) -> dict:
    audiences = configured_google_audiences(settings)
    try:
        claims = google_id_token.verify_oauth2_token(
            token,
            GoogleRequest(),
            audience=audiences[0] if len(audiences) == 1 else audiences,
        )
    except ValueError as exc:
        raise unauthorized() from exc
    except google_exceptions.GoogleAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google authentication service unavailable",
        ) from exc
    if (
        not isinstance(claims.get("sub"), str)
        or not claims["sub"]
        or not isinstance(claims.get("email"), str)
        or claims.get("email_verified") is not True
    ):
        raise unauthorized()
    return claims


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    request: RegisterRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    signing_secret(settings)
    email = normalize_email(str(request.email))
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Account already exists")

    user = User(
        email=email,
        password_hash=password_hasher.hash(request.password),
        role=request.role,
    )
    db.add(user)
    try:
        db.flush()
        add_student_profile(db, user, request.student_profile)
        tokens = issue_tokens(db, user, settings)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Account already exists") from exc
    return tokens


@router.post("/login", response_model=TokenResponse)
def login(
    request: LoginRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    signing_secret(settings)
    user = db.scalar(select(User).where(User.email == normalize_email(str(request.email))))
    encoded_password = user.password_hash if user and user.password_hash else dummy_password_hash
    password_valid = password_hasher.verify(request.password, encoded_password)
    if user is None or user.password_hash is None or not password_valid:
        raise unauthorized()
    tokens = issue_tokens(db, user, settings)
    db.commit()
    return tokens


@router.post("/google", response_model=TokenResponse)
def google_sign_in(
    request: GoogleSignInRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    signing_secret(settings)
    claims = verify_google_token(request.id_token, settings)
    email = normalize_email(claims["email"])
    user = db.scalar(select(User).where(User.google_sub == claims["sub"]))
    if user is not None:
        if user.email != email:
            existing_email = db.scalar(select(User.id).where(User.email == email))
            if existing_email is not None and existing_email != user.id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Account already exists")
            user.email = email
    else:
        user = db.scalar(select(User).where(User.email == email))
        if user is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Account already exists")
        if user is None:
            if request.role == "student" and request.student_profile is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="student_profile is required for new student accounts",
                )
            if request.role == "freelancer" and request.student_profile is not None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="student_profile is only valid for student accounts",
                )
            user = User(email=email, google_sub=claims["sub"], role=request.role)
            db.add(user)
            try:
                db.flush()
                add_student_profile(db, user, request.student_profile)
            except IntegrityError as exc:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Account already exists",
                ) from exc
    tokens = issue_tokens(db, user, settings)
    db.commit()
    return tokens


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    request: RefreshRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    signing_secret(settings)
    token_hash = hash_refresh_token(request.refresh_token)
    user_id = db.scalar(
        select(RefreshSession.user_id).where(RefreshSession.token_hash == token_hash)
    )
    if user_id is None:
        raise unauthorized()

    # Serialize refresh and replay handling across sessions owned by this user.
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None:
        raise unauthorized()
    session = db.scalar(
        select(RefreshSession)
        .where(RefreshSession.token_hash == token_hash)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if session is None:
        raise unauthorized()

    now = datetime.now(UTC)
    if session.revoked_at is not None:
        db.execute(
            update(RefreshSession)
            .where(
                RefreshSession.family_id == session.family_id,
                RefreshSession.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        db.commit()
        raise unauthorized()
    if session.expires_at <= now:
        session.revoked_at = now
        db.commit()
        raise unauthorized()

    family_id = session.family_id
    session.revoked_at = now
    tokens = issue_tokens(db, user, settings, family_id=family_id)
    db.commit()
    return tokens


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: RefreshRequest, db: Session = Depends(get_db)) -> Response:
    token_hash = hash_refresh_token(request.refresh_token)
    user_id = db.scalar(select(RefreshSession.user_id).where(RefreshSession.token_hash == token_hash))
    if user_id is not None:
        db.scalar(select(User).where(User.id == user_id).with_for_update())
        session = db.scalar(
            select(RefreshSession)
            .where(RefreshSession.token_hash == token_hash)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if session is not None:
            db.execute(
                update(RefreshSession)
                .where(
                    RefreshSession.family_id == session.family_id,
                    RefreshSession.revoked_at.is_(None),
                )
                .values(revoked_at=datetime.now(UTC))
            )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
