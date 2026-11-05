from datetime import UTC, datetime
import hmac
import secrets
from datetime import timedelta
from hashlib import sha256
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from google.auth import exceptions as google_exceptions
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token as google_id_token
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, EmailStr, Field, StringConstraints, UrlConstraints, model_validator
from pwdlib import PasswordHash
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import hash_refresh_token, issue_tokens, signing_secret
from app.core.email import send_auth_email
from app.core.config import Settings, get_settings
from app.db.models import AuthToken, RefreshSession, StudentProfile, User
from app.db.session import get_db

router = APIRouter(
    prefix="/auth",
    tags=["authentication"],
    responses={
        422: {"description": "A request field failed validation."},
        503: {"description": "Authentication service or required configuration is unavailable."},
    },
)
password_hasher = PasswordHash.recommended()
dummy_password_hash = password_hasher.hash("bridge-invalid-login-placeholder")
RoleChoice = Literal["student", "freelancer"]
Skill = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


class CoreSkillInput(BaseModel):
    name: Skill
    depth: Literal["beginner", "intermediate", "advanced"]


class StudentProfileInput(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "full_name": "Ayesha Khan",
        "key_skills": ["Python", "FastAPI"],
        "experience_level": "intermediate",
        "availability_hours_per_week": 20,
        "portfolio_url": "https://example.com/portfolio",
    }]})

    full_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)] | None = None
    key_skills: list[Skill] | None = Field(default=None, max_length=20)
    experience_level: Literal["beginner", "intermediate", "advanced"] | None = None
    availability_hours_per_week: int | None = Field(default=None, ge=0, le=168)
    portfolio_url: Annotated[AnyHttpUrl, UrlConstraints(max_length=2048)] | None = Field(
        default=None, description="Optional HTTP(S) portfolio URL."
    )
    university: str | None = Field(default=None, max_length=200)
    degree_program: str | None = Field(default=None, max_length=200)
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
    def skills_are_unique(self):
        all_skills = (self.key_skills or []) + [skill.name for skill in self.core_skills or []] + (self.supporting_skills or [])
        if len({skill.casefold() for skill in all_skills}) != len(all_skills):
            raise ValueError("skills must be unique")
        if self.preferred_work_types is not None and len(set(self.preferred_work_types)) != len(self.preferred_work_types):
            raise ValueError("preferred_work_types must be unique")
        return self


class RegisterRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "email": "student@example.com",
        "password": "ExamplePass123!",
        "role": "student",
        "student_profile": {
            "full_name": "Ayesha Khan",
            "key_skills": ["Python", "FastAPI"],
            "experience_level": "intermediate",
            "availability_hours_per_week": 20,
            "portfolio_url": "https://example.com/portfolio",
        },
    }]})

    email: EmailStr = Field(description="Account email address.")
    password: str = Field(min_length=8, max_length=128, description="Password (8–128 characters).")
    role: RoleChoice = Field(default="student", description="Public signup role: student or freelancer.")
    student_profile: StudentProfileInput | None = Field(
        default=None, description="Required for student signup; omitted for freelancer signup."
    )

    @model_validator(mode="after")
    def require_student_profile(self):
        if self.role == "student" and self.student_profile is None:
            raise ValueError("student_profile is required for student accounts")
        if self.role == "student":
            first_step = ("full_name", "university", "degree_program", "graduation_year", "profile_photo_url")
            legacy_profile = ("full_name", "key_skills", "experience_level", "availability_hours_per_week")
            if not all(getattr(self.student_profile, field) is not None for field in first_step) and not all(
                getattr(self.student_profile, field) is not None for field in legacy_profile
            ):
                raise ValueError("provide the first profile step to sign up")
        if self.role == "freelancer" and self.student_profile is not None:
            raise ValueError("student_profile is only valid for student accounts")
        return self


class LoginRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "email": "student@example.com",
        "password": "ExamplePass123!",
    }]})

    email: EmailStr = Field(description="Account email address.")
    password: str = Field(min_length=1, max_length=128, description="Account password.")


class GoogleSignInRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "id_token": "<google-id-token>",
        "role": "student",
        "student_profile": {
            "full_name": "Ayesha Khan",
            "key_skills": ["Python", "FastAPI"],
            "experience_level": "intermediate",
            "availability_hours_per_week": 20,
            "portfolio_url": "https://example.com/portfolio",
        },
    }]})

    id_token: str = Field(min_length=1, max_length=8192, description="Google ID token obtained by the mobile Google Sign-In SDK.")
    role: RoleChoice = Field(default="student", description="Role for a new Bridge account; existing accounts keep their saved role.")
    student_profile: StudentProfileInput | None = Field(
        default=None, description="Required when creating a new student account; omitted for freelancer signup."
    )


class RefreshRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"refresh_token": "<bridge-refresh-token>"}]})

    refresh_token: str = Field(min_length=1, max_length=512, description="Bridge refresh token returned at sign-in.")


class TokenResponse(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "access_token": "<bridge-access-token>",
        "refresh_token": "<bridge-refresh-token>",
        "token_type": "bearer",
        "expires_in": 900,
    }]})

    access_token: str = Field(description="Bridge JWT to send as a bearer token to protected endpoints.")
    refresh_token: str = Field(description="Opaque Bridge token used only with refresh and logout endpoints.")
    token_type: Literal["bearer"] = Field(default="bearer", description="Access-token scheme.")
    expires_in: int = Field(description="Access-token lifetime in seconds.")


class EmailRequest(BaseModel):
    email: EmailStr


class TokenRequest(BaseModel):
    token: str = Field(min_length=20, max_length=512)


class EmailVerificationRequest(BaseModel):
    email: EmailStr | None = None
    code: str | None = Field(default=None, pattern=r"^\d{8}$")
    token: str | None = Field(default=None, min_length=20, max_length=512)

    @model_validator(mode="after")
    def require_code_or_legacy_link(self):
        if self.token is not None:
            if self.email is not None or self.code is not None:
                raise ValueError("send either token or email and code")
        elif self.email is None or self.code is None:
            raise ValueError("email and an 8-digit code are required")
        return self


class PasswordResetRequest(TokenRequest):
    password: str = Field(min_length=8, max_length=128)


class MessageResponse(BaseModel):
    message: str


def create_auth_token(db: Session, user: User, purpose: str) -> str:
    raw = secrets.token_urlsafe(32)
    db.add(AuthToken(user_id=user.id, purpose=purpose, token_hash=sha256(raw.encode()).hexdigest(), expires_at=datetime.now(UTC) + timedelta(hours=1)))
    return raw


def create_verification_code(db: Session, user: User, settings: Settings) -> str:
    code = f"{secrets.randbelow(100_000_000):08d}"
    token_hash = hmac.digest(signing_secret(settings).encode(), code.encode(), "sha256").hex()
    db.add(AuthToken(
        user_id=user.id,
        purpose="verify_email",
        token_hash=token_hash,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    ))
    return code


def token_expired(expires_at: datetime, now: datetime) -> bool:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= now


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def add_student_profile(db: Session, user: User, profile: StudentProfileInput | None) -> None:
    if profile is not None:
        db.add(
            StudentProfile(
                user_id=user.id,
                full_name=profile.full_name,
                key_skills=profile.key_skills or [],
                experience_level=profile.experience_level,
                availability_hours_per_week=profile.availability_hours_per_week,
                portfolio_url=str(profile.portfolio_url) if profile.portfolio_url else None,
                university=profile.university,
                degree_program=profile.degree_program,
                graduation_year=profile.graduation_year,
                profile_photo_url=str(profile.profile_photo_url) if profile.profile_photo_url else None,
                highlights=profile.highlights,
                digital_footprint=[str(url) for url in profile.digital_footprint or []],
                core_skills=[skill.model_dump() for skill in profile.core_skills or []],
                supporting_skills=profile.supporting_skills or [],
                availability=profile.availability,
                preferred_work_types=profile.preferred_work_types or [],
                workplace_arrangement=profile.workplace_arrangement,
                project_duration=profile.project_duration,
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


@router.post(
    "/register",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a Bridge account",
    responses={409: {"description": "An account with this email already exists."}, 422: {"description": "Request fields failed validation."}, 503: {"description": "Required authentication configuration is unavailable."}},
)
def register(
    request: RegisterRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Create an account and send an email verification code."""
    signing_secret(settings)
    email = normalize_email(str(request.email))
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Account already exists")

    user = User(
        email=email,
        password_hash=password_hasher.hash(request.password),
        role=request.role,
        email_verified=False,
    )
    db.add(user)
    try:
        db.flush()
        add_student_profile(db, user, request.student_profile)
        code = create_verification_code(db, user, settings)
        send_auth_email(settings, email, "Verify your Bridge email", f"Your verification code is {code}. It expires in 10 minutes.\n")
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Account already exists") from exc
    return {"message": "Check your email to verify your account."}


@router.post("/verify-email", response_model=MessageResponse)
def verify_email(
    request: EmailVerificationRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    now = datetime.now(UTC)
    if request.token is not None:
        token_hash = sha256(request.token.encode()).hexdigest()
        user_id = db.scalar(select(AuthToken.user_id).where(
            AuthToken.token_hash == token_hash,
            AuthToken.purpose == "verify_email",
        ))
        user = db.scalar(select(User).where(User.id == user_id).with_for_update()) if user_id else None
        record = db.scalar(select(AuthToken).where(
            AuthToken.token_hash == token_hash,
            AuthToken.purpose == "verify_email",
        ).with_for_update().execution_options(populate_existing=True)) if user else None
        candidate_hash = record.token_hash if record is not None else ""
    else:
        user = db.scalar(select(User).where(
            User.email == normalize_email(str(request.email))
        ).with_for_update())
        record = db.scalar(select(AuthToken).where(
            AuthToken.user_id == user.id,
            AuthToken.purpose == "verify_email",
            AuthToken.used_at.is_(None),
        ).order_by(AuthToken.created_at.desc()).limit(1).with_for_update()) if user else None
        candidate_hash = hmac.digest(
            signing_secret(settings).encode(), request.code.encode(), "sha256"
        ).hex()
    if record is None or record.used_at is not None or record.failed_attempts >= 5 or token_expired(record.expires_at, now):
        raise HTTPException(status_code=400, detail="Verification code is invalid or expired")
    if request.token is None and not hmac.compare_digest(record.token_hash, candidate_hash):
        record.failed_attempts += 1
        if record.failed_attempts >= 5:
            record.used_at = now
        db.commit()
        raise HTTPException(status_code=400, detail="Verification code is invalid or expired")
    if user is None:
        raise HTTPException(status_code=400, detail="Verification code is invalid or expired")
    user.email_verified = True
    record.used_at = now
    db.execute(update(AuthToken).where(
        AuthToken.user_id == user.id,
        AuthToken.purpose == "verify_email",
        AuthToken.used_at.is_(None),
        AuthToken.id != record.id,
    ).values(used_at=now))
    db.commit()
    return {"message": "Email verified."}


@router.post("/resend-verification", response_model=MessageResponse)
def resend_verification(
    request: EmailRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    response = {"message": "If the account exists and needs verification, a code has been sent."}
    user = db.scalar(select(User).where(User.email == normalize_email(str(request.email))).with_for_update())
    if user is None or user.email_verified or user.password_hash is None:
        return response
    now = datetime.now(UTC)
    latest = db.scalar(select(AuthToken).where(
        AuthToken.user_id == user.id,
        AuthToken.purpose == "verify_email",
    ).order_by(AuthToken.created_at.desc()).limit(1).with_for_update())
    if latest is not None:
        created_at = latest.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        if now - created_at < timedelta(seconds=60):
            return response
    db.execute(update(AuthToken).where(
        AuthToken.user_id == user.id,
        AuthToken.purpose == "verify_email",
        AuthToken.used_at.is_(None),
    ).values(used_at=now))
    code = create_verification_code(db, user, settings)
    db.commit()
    try:
        send_auth_email(settings, user.email, "Verify your Bridge email", f"Your verification code is {code}. It expires in 10 minutes.\n")
    except HTTPException:
        pass
    return response


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(request: EmailRequest, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    user = db.scalar(select(User).where(User.email == normalize_email(str(request.email))))
    if user is not None and user.password_hash is not None:
        token = create_auth_token(db, user, "reset_password")
        db.commit()
        try:
            send_auth_email(settings, user.email, "Reset your Bridge password", f"Reset your password using this link: {settings.public_app_url.rstrip('/')}/reset-password?token={token}\n")
        except HTTPException:
            pass
    return {"message": "If the account exists, password reset instructions have been sent."}


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(request: PasswordResetRequest, db: Session = Depends(get_db)) -> dict:
    now = datetime.now(UTC)
    record = db.scalar(select(AuthToken).where(AuthToken.token_hash == sha256(request.token.encode()).hexdigest(), AuthToken.purpose == "reset_password").with_for_update())
    if record is None or record.used_at is not None or token_expired(record.expires_at, now):
        raise HTTPException(status_code=400, detail="Password reset link is invalid or expired")
    user = db.get(User, record.user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="Password reset link is invalid or expired")
    user.password_hash = password_hasher.hash(request.password)
    record.used_at = now
    db.execute(update(RefreshSession).where(RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None)).values(revoked_at=now))
    db.commit()
    return {"message": "Password has been reset."}


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Sign in with email and password",
    responses={401: {"description": "Email or password is invalid."}, 503: {"description": "Authentication is not configured."}},
)
def login(
    request: LoginRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Verify credentials and return Bridge access and refresh tokens."""
    signing_secret(settings)
    user = db.scalar(select(User).where(User.email == normalize_email(str(request.email))))
    encoded_password = user.password_hash if user and user.password_hash else dummy_password_hash
    password_valid = password_hasher.verify(request.password, encoded_password)
    if user is None or user.password_hash is None or not password_valid or not user.email_verified:
        raise unauthorized()
    tokens = issue_tokens(db, user, settings)
    db.commit()
    return tokens


@router.post(
    "/google",
    response_model=TokenResponse,
    summary="Sign in with Google",
    responses={401: {"description": "Google ID token is invalid."}, 409: {"description": "Email already belongs to a different account."}, 503: {"description": "Google sign-in is unavailable or not configured."}},
)
def google_sign_in(
    request: GoogleSignInRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Exchange a Google ID token for Bridge tokens; new student accounts need a profile."""
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


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh Bridge tokens",
    responses={401: {"description": "Refresh token is invalid, expired, or reused."}, 503: {"description": "Authentication is not configured."}},
)
def refresh(
    request: RefreshRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Rotate a refresh token and return a new access/refresh token pair."""
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


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Log out",
    description="Revoke the refresh token's session family. Returns 204 with no response body.",
)
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
