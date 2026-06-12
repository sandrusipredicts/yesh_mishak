from fastapi import FastAPI

from app.api.auth import router as auth_router

app = FastAPI(title="yesh_mishak API")

app.include_router(auth_router)


@app.get("/")
def read_root() -> dict[str, str]:
    return {"status": "ok"}
