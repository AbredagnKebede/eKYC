import logging
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from src.infrastructure.redis import get_redis_client
from src.models.base import async_session_factory
from src.services.bank_adapter import BankNotFoundError, BankSchemaValidationError
from src.services.identity import (
    FaydaError,
    FaydaFormatError,
    FaydaVerificationError,
    IdentityNotFoundError,
    InvalidStateError,
    LivenessVerificationError,
)
from src.services.onboarding import (
    ApplicationNotFoundError,
    StateGuardError,
    StateTransitionError,
)

from src.api.middleware import RateLimitMiddleware, SecurityHeadersMiddleware
from src.api.routes.applications import router as applications_router
from src.api.routes.banks import router as banks_router

logger = logging.getLogger("ekyc.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager initializing resources on startup and cleaning up on shutdown."""
    logger.info("Starting eKYC API Gateway...")
    try:
        from src.models.base import async_session_factory, init_models
        from src.models.schema_ensure import ensure_schema_extensions
        from src.api.routes.bank_portal import bootstrap_bank_portal_staff

        await init_models()
        await ensure_schema_extensions()
        logger.info("Database tables initialized.")
        async with async_session_factory() as session:
            n = await bootstrap_bank_portal_staff(session)
            await session.commit()
            logger.info("Bank portal bootstrap: %s new super admins", n)
    except Exception as exc:
        logger.warning("Database initialization deferred: %s", exc)
    yield
    logger.info("Shutting down eKYC API Gateway...")
    redis_client = get_redis_client()
    await redis_client.aclose()


def create_app() -> FastAPI:
    """Application factory configuring middleware, exception handlers, and API routers."""
    app = FastAPI(
        title="eKYC National Identity Onboarding API Gateway",
        description="Self-Service Bank Onboarding Platform integrated with Fayda National ID (NIDP)",
        version="1.0.0",
        lifespan=lifespan,
    )

    # 1. CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2. Security Headers Middleware
    app.add_middleware(SecurityHeadersMiddleware)

    # 3. Sliding Window Rate Limiter Middleware
    app.add_middleware(RateLimitMiddleware, max_requests=120, window_seconds=60)

    # 4. Global Exception Handlers conforming to RFC 7807 Problem Details
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        content: Dict[str, Any]
        if isinstance(exc.detail, dict):
            content = exc.detail
            content.setdefault("instance", request.url.path)
            content.setdefault("status", exc.status_code)
        else:
            title_map = {
                400: "Bad Request",
                401: "Unauthorized",
                403: "Forbidden",
                404: "Not Found",
                409: "Conflict",
                422: "Unprocessable Entity",
                429: "Too Many Requests",
                500: "Internal Server Error",
                502: "Bad Gateway",
                503: "Service Unavailable",
            }
            content = {
                "type": f"https://errors.ekyc.et/{exc.status_code}",
                "title": title_map.get(exc.status_code, "HTTP Error"),
                "status": exc.status_code,
                "detail": str(exc.detail),
                "instance": request.url.path,
            }
        return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)

    @app.exception_handler(ApplicationNotFoundError)
    async def application_not_found_handler(request: Request, exc: ApplicationNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "type": "https://errors.ekyc.et/APPLICATION_NOT_FOUND",
                "title": "Application Not Found",
                "status": 404,
                "detail": str(exc),
                "instance": request.url.path,
            },
        )

    @app.exception_handler(BankSchemaValidationError)
    async def schema_validation_handler(request: Request, exc: BankSchemaValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "type": "https://errors.ekyc.et/INVALID_DYNAMIC_FIELDS",
                "title": "Dynamic Schema Validation Failed",
                "status": 400,
                "detail": str(exc),
                "field_errors": exc.field_errors,
                "instance": request.url.path,
            },
        )

    @app.exception_handler(StateTransitionError)
    @app.exception_handler(StateGuardError)
    @app.exception_handler(InvalidStateError)
    async def state_error_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "type": "https://errors.ekyc.et/INVALID_STATE_TRANSITION",
                "title": "Invalid State Transition",
                "status": 409,
                "detail": str(exc),
                "instance": request.url.path,
            },
        )

    # 5. Core Health & Liveness Endpoints
    @app.get("/health", tags=["Health"])
    @app.get("/health/live", tags=["Health"])
    async def health_check() -> Dict[str, str]:
        """Simple liveness probe reporting service status."""
        return {"status": "healthy", "service": "ekyc-api-gateway"}

    @app.get("/health/ready", tags=["Health"])
    async def readiness_probe() -> JSONResponse:
        """Deep readiness probe checking real database and Redis connectivity."""
        db_healthy = False
        redis_healthy = False

        try:
            async with async_session_factory() as session:
                await session.execute(text("SELECT 1"))
                db_healthy = True
        except Exception as db_exc:
            logger.warning("Readiness probe: Database unavailable: %s", db_exc)

        try:
            redis_client = get_redis_client()
            pong = await redis_client.ping()
            redis_healthy = bool(pong)
        except Exception as redis_exc:
            logger.warning("Readiness probe: Redis unavailable: %s", redis_exc)

        is_ready = db_healthy and redis_healthy
        status_code = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE
        return JSONResponse(
            status_code=status_code,
            content={
                "status": "ready" if is_ready else "degraded",
                "components": {
                    "database": "connected" if db_healthy else "disconnected",
                    "redis": "connected" if redis_healthy else "disconnected",
                },
            },
        )

    # 6. Mount API Routers
    from src.api.routes.ops import router as ops_router
    from src.api.routes.bank_portal import router as bank_portal_router

    app.include_router(banks_router)
    app.include_router(applications_router)
    app.include_router(ops_router)
    app.include_router(bank_portal_router)

    # 7. Tester landing page + APK downloads + bank portal
    static_root = Path(__file__).resolve().parents[2] / "static"
    releases_dir = static_root / "releases"
    releases_dir.mkdir(parents=True, exist_ok=True)
    portal_dir = static_root / "bank-portal"
    portal_dir.mkdir(parents=True, exist_ok=True)
    if static_root.exists():
        app.mount("/static", StaticFiles(directory=str(static_root)), name="static")

    @app.get("/", include_in_schema=False)
    async def tester_home() -> FileResponse:
        return FileResponse(static_root / "testers" / "index.html")

    @app.get("/testers", include_in_schema=False)
    async def tester_page() -> FileResponse:
        return FileResponse(static_root / "testers" / "index.html")

    @app.get("/ops", include_in_schema=False)
    async def ops_console() -> FileResponse:
        return FileResponse(static_root / "ops" / "index.html")

    @app.get("/bank-portal", include_in_schema=False)
    @app.get("/bank-portal/", include_in_schema=False)
    async def bank_portal_home():
        """Prefer the Vercel Next.js portal when BANK_PORTAL_URL is set."""
        from fastapi.responses import RedirectResponse

        portal_url = (os.getenv("BANK_PORTAL_URL") or "").strip()
        if portal_url:
            return RedirectResponse(url=portal_url, status_code=307)
        index = portal_dir / "index.html"
        if not index.exists():
            raise HTTPException(
                status_code=404,
                detail="Bank portal UI not configured. Deploy bank-portal/ on Vercel or set BANK_PORTAL_URL.",
            )
        return FileResponse(index)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=True)
