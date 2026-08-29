from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.middleware import RequestLoggingMiddleware, RateLimitMiddleware
from app.api.v1.router import api_router
from app.db.session import init_db, close_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        description=settings.PROJECT_DESCRIPTION,
        version=settings.VERSION,
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
        docs_url=f"{settings.API_V1_PREFIX}/docs",
        redoc_url=f"{settings.API_V1_PREFIX}/redoc",
        lifespan=lifespan,
    )

    from fastapi.exceptions import RequestValidationError
    from starlette.middleware.base import BaseHTTPMiddleware
    import structlog
    logger = structlog.get_logger(__name__)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        logger.error(
            "Validation error in request",
            errors=exc.errors(),
            url=str(request.url),
        )
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.error("Unhandled exception", exc_info=exc, url=str(request.url))
        return JSONResponse(
            status_code=500,
            content={"detail": "Error interno del servidor"},
        )

    # Safety net: catch any unhandled exception and return JSON
    # This MUST be OUTSIDE CORSMiddleware so its responses get CORS headers
    class CatchAllMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            try:
                return await call_next(request)
            except Exception as e:
                logger.error("Unhandled middleware exception", exc_info=e, path=request.url.path)
                return JSONResponse(
                    status_code=500,
                    content={"detail": "Error interno del servidor"},
                )

    app.add_middleware(CatchAllMiddleware)

    # Compression (must be first to compress all responses)
    app.add_middleware(GZipMiddleware, minimum_size=500)

    # Security middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_origin_regex=settings.CORS_ORIGIN_REGEX,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)

    # Custom middleware
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RateLimitMiddleware)

    # Page view tracking middleware
    from app.core.page_view_tracker import record_view

    @app.middleware("http")
    async def track_page_views(request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if (
            path.startswith("/v1/")
            and not path.startswith("/v1/auth/")
            and not path.startswith("/v1/dashboard/")
            and not path.startswith("/v1/storage/")
            and request.method == "GET"
        ):
            try:
                visitor = request.headers.get("x-forwarded-for", "anon").split(",")[0].strip()
                record_view(path, visitor)
            except Exception:
                pass
        return response

    # Routes
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    # Health check
    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "version": settings.VERSION}

    @app.get("/")
    async def root():
        return {
            "name": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "docs": f"{settings.API_V1_PREFIX}/docs",
        }

    return app


app = create_app()