from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.v1.router import router as v1_router

app = FastAPI(
    title="Bridge API",
    version="0.1.0",
    description=(
        "Authenticated API for Bridge accounts, profiles, tasks, and applications. "
        "Use the interactive Swagger UI at `/docs` or the OpenAPI JSON at `/openapi.json`. "
        "Protected endpoints use `Authorization: Bearer <access_token>`; budgets are PKR and "
        "task deadlines are ISO 8601 calendar dates."
    ),
    openapi_tags=[
        {"name": "authentication", "description": "Register or sign in, then manage Bridge token sessions."},
        {"name": "identity", "description": "Read the authenticated Bridge account and student profile."},
        {"name": "freelancer-profiles", "description": "Save and publish freelancer onboarding profiles."},
        {"name": "tasks", "description": "Freelancer task listings and student proposals."},
    ],
)
app.include_router(health_router)
app.include_router(v1_router, prefix="/v1")
