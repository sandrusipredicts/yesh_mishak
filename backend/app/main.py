from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.routers import fields, games

app = FastAPI(title="yesh_mishak API", version="0.1.0")

app.include_router(auth_router)
app.include_router(fields.router)
app.include_router(games.router)


@app.get("/")
def read_root():
    return {"status": "ok"}