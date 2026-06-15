from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.core.config import get_settings
from app.routers import fields, games, notifications

app = FastAPI(title="yesh_mishak API", version="0.1.0")
settings = get_settings()
cors_origins = [
    origin.strip()
    for origin in settings.cors_origins.split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_router)
app.include_router(auth_router)
app.include_router(fields.router)
app.include_router(games.router)
app.include_router(notifications.router)


@app.get("/")
def read_root():
    return {"status": "ok"}
