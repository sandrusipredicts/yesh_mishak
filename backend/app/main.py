from fastapi import FastAPI

app = FastAPI(title="yesh_mishak API")


@app.get("/")
def read_root() -> dict[str, str]:
    return {"status": "ok"}
