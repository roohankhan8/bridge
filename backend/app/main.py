from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.v1.router import router as v1_router

app = FastAPI(title="Bridge API", version="0.1.0")
app.include_router(health_router)
app.include_router(v1_router, prefix="/v1")
