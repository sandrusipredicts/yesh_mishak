from fastapi import FastAPI
from app.routers import fields

app = FastAPI(title="yesh_mishak API")

app.include_router(fields.router)


@app.get("/")
def read_root() -> dict[str, str]:
    return {"status": "ok"}