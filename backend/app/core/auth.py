import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from fastapi import HTTPException, status
from jwt.exceptions import PyJWTError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import RefreshSession, User

ACCESS_TOKEN_LIFETIME = timedelta(minutes=15)
REFRESH_TOKEN_LIFETIME = timedelta(days=30)
JWT_ISSUER = "bridge-api"
JWT_AUDIENCE = "bridge-api"


def signing_secret(settings: Settings) -> str:
    secret = settings.auth_jwt_secret
    if not secret or len(secret.encode("utf-8")) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        )
    return secret


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_tokens(
    db: Session,
    user: User,
    settings: Settings,
    family_id: UUID | None = None,
) -> dict[str, str | int]:
    now = datetime.now(UTC)
    access_token = jwt.encode(
        {
            "sub": str(user.id),
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
            "iat": now,
            "exp": now + ACCESS_TOKEN_LIFETIME,
            "jti": str(uuid4()),
            "token_type": "access",
        },
        signing_secret(settings),
        algorithm="HS256",
    )
    refresh_token = secrets.token_urlsafe(48)
    db.add(
        RefreshSession(
            user_id=user.id,
            family_id=family_id or uuid4(),
            token_hash=hash_refresh_token(refresh_token),
            expires_at=now + REFRESH_TOKEN_LIFETIME,
        )
    )
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": int(ACCESS_TOKEN_LIFETIME.total_seconds()),
    }


def decode_access_token(token: str, settings: Settings) -> UUID:
    try:
        claims = jwt.decode(
            token,
            signing_secret(settings),
            algorithms=["HS256"],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
            options={"require": ["exp", "iat", "iss", "aud", "sub", "jti", "token_type"]},
        )
        if claims.get("token_type") != "access":
            raise PyJWTError("Wrong token type")
        return UUID(claims["sub"])
    except HTTPException:
        raise
    except (PyJWTError, ValueError, TypeError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
