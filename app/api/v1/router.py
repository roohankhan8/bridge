from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.me import router as me_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.freelancer_profile import router as freelancer_profile_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(me_router, tags=["identity"])
router.include_router(tasks_router)
router.include_router(freelancer_profile_router, tags=["freelancer-profiles"])
