from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.dependencies import get_current_user

router = APIRouter()


class IdentityResponse(BaseModel):
    user_id: str


@router.get("/me", response_model=IdentityResponse)
def read_current_user(claims: dict = Depends(get_current_user)) -> IdentityResponse:
    return IdentityResponse(user_id=claims["sub"])
