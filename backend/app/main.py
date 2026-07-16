import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException, RequestValidationError

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.core.config import get_settings
from app.middleware.request_metrics import request_metrics_middleware
from app.routers import field_reports, fields, games, notifications, share_events

logger = logging.getLogger("app")

app = FastAPI(title="yesh_mishak API", version="0.1.0")

# Global exception handlers for standardizing API error responses
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # Check if detail is already our structured dictionary
    if isinstance(exc.detail, dict) and exc.detail.get("error") is True:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    
    # Otherwise, it's a string, or unmapped exception. Map status_code to standard codes:
    status_code = exc.status_code
    message = str(exc.detail)
    
    if status_code == 400:
        code = "BAD_REQUEST"
    elif status_code == 401:
        code = "AUTH_REQUIRED"
    elif status_code == 403:
        code = "FORBIDDEN"
    elif status_code == 404:
        code = "NOT_FOUND"
    elif status_code == 409:
        code = "CONFLICT"
    elif status_code == 422:
        code = "VALIDATION_ERROR"
    else:
        code = "INTERNAL_SERVER_ERROR"
        
    return JSONResponse(
        status_code=status_code,
        content={
            "error": True,
            "code": code,
            "message": message
        }
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    details = {}
    for error in exc.errors():
        loc = error.get("loc", [])
        if len(loc) > 1:
            field = ".".join(str(x) for x in loc[1:])
        elif len(loc) == 1:
            field = str(loc[0])
        else:
            field = "non_field_error"
        details[field] = error.get("msg", "Invalid value")
        
    return JSONResponse(
        status_code=422,
        content={
            "error": True,
            "code": "VALIDATION_ERROR",
            "message": "Validation failed",
            "details": details
        }
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error occurred during request processing")
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "code": "INTERNAL_SERVER_ERROR",
            "message": "An internal server error occurred"
        }
    )

settings = get_settings()
cors_origins = [
    origin.strip()
    for origin in settings.cors_origins.split(",")
    if origin.strip()
]
for local_origin in (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
):
    if local_origin not in cors_origins:
        cors_origins.append(local_origin)

# Canonical production frontend origin.
for production_origin in ("https://yesh-mishak.com",):
    if production_origin not in cors_origins:
        cors_origins.append(production_origin)

# The Capacitor Android WebView always loads the bundled app from this fixed
# origin (Capacitor's default androidScheme is "https"), in every build
# variant including release. Browsers set the Origin header from the actual
# page origin, so only the app's own WebView can send this Origin - it is
# not a wildcard and does not expose the API to arbitrary websites.
for mobile_app_origin in ("https://localhost",):
    if mobile_app_origin not in cors_origins:
        cors_origins.append(mobile_app_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(request_metrics_middleware)

app.include_router(admin_router)
app.include_router(auth_router)
app.include_router(field_reports.router)
app.include_router(fields.router)
app.include_router(games.router)
app.include_router(notifications.router)
app.include_router(share_events.router)


@app.get("/")
def read_root():
    return {"status": "ok"}

