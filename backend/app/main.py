"""
CodeInsight AI - FastAPI application entrypoint.

Run locally with:
    uvicorn app.main:app --reload --port 8000
"""
import logging

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import analyze, auth, github, health, projects, tasks
from app.core.config import get_settings
from app.core.logging_config import configure_logging

settings = get_settings()
configure_logging(debug=settings.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.APP_NAME,
    description="AI-assisted static code review and bug detection platform.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_DOCS_PATHS = {"/docs", "/redoc", "/openapi.json"}


@app.middleware("http")
async def add_secure_headers(request: Request, call_next):
    """Baseline secure response headers (Phase 5).

    A strict Content-Security-Policy is skipped on /docs and /redoc since
    Swagger/ReDoc's UI loads its own JS/CSS and a strict CSP would break
    it; every other response gets the full set.
    """
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    # Meaningless over plain HTTP but harmless to always send -- browsers
    # only honor it once a connection is actually HTTPS.
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    if request.url.path not in _DOCS_PATHS:
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    return response


app.include_router(health.router, prefix=settings.API_PREFIX)
app.include_router(auth.router, prefix=settings.API_PREFIX)
app.include_router(projects.router, prefix=settings.API_PREFIX)
app.include_router(analyze.router, prefix=settings.API_PREFIX)
app.include_router(tasks.router, prefix=settings.API_PREFIX)
app.include_router(github.router, prefix=settings.API_PREFIX)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Return clean, structured 422s instead of default FastAPI tracebacks.
    # Pydantic v2 puts raw exception objects in error["ctx"]["error"], which
    # json.dumps can't serialize on its own -- jsonable_encoder normalizes those
    # (via str()) so we always return valid JSON instead of a 500.
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Invalid request.",
            "errors": jsonable_encoder(exc.errors()),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s", request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal error occurred."},
    )


@app.get("/")
def root():
    return {"app": settings.APP_NAME, "status": "running", "docs": "/docs"}
