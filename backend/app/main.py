# backend/app/main.py
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.api.routes import router
from app.api.middleware import (
    RequestLoggingMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    RequestSizeLimitMiddleware,
    AuditLogMiddleware,
)

# ─── Logging Configuration ────────────────────────────────────

def setup_logging() -> None:
    """Configure application logging."""
    log_format = (
        "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
    )
    
    handlers = [logging.StreamHandler(sys.stdout)]
    
    if not settings.DEBUG:
        # Add file handler in production
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        handlers.append(
            logging.FileHandler(log_dir / "app.log", encoding="utf-8")
        )
        
        # Separate audit log
        audit_handler = logging.FileHandler(log_dir / "audit.log", encoding="utf-8")
        audit_handler.setLevel(logging.INFO)
        audit_logger = logging.getLogger("audit")
        audit_logger.addHandler(audit_handler)
        audit_logger.setLevel(logging.INFO)
    
    logging.basicConfig(
        level=logging.DEBUG if settings.DEBUG else logging.INFO,
        format=log_format,
        handlers=handlers,
    )
    
    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

setup_logging()
logger = logging.getLogger(__name__)


# ─── Application Lifespan ─────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application startup and shutdown lifecycle management.
    """
    logger.info("=" * 60)
    logger.info("Starting MPesa Statement Processor")
    logger.info(f"Environment: {'Development' if settings.DEBUG else 'Production'}")
    logger.info("=" * 60)
    
    # Startup: Create required directories
    try:
        settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"Upload directory: {settings.UPLOAD_DIR}")
        logger.info(f"Output directory: {settings.OUTPUT_DIR}")
    except Exception as e:
        logger.error(f"Failed to create directories: {e}")
        raise
    
    # Startup: Clean up any stale files from previous runs
    await cleanup_stale_files()
    
    yield  # Application runs here
    
    # Shutdown: Cleanup
    logger.info("Shutting down application...")
    await cleanup_stale_files()
    logger.info("Shutdown complete")


async def cleanup_stale_files() -> None:
    """Remove any stale temporary files."""
    import asyncio
    from datetime import datetime, timedelta
    
    cutoff = datetime.now() - timedelta(hours=1)
    
    for directory in [settings.UPLOAD_DIR, settings.OUTPUT_DIR]:
        if not directory.exists():
            continue
        
        for file_path in directory.iterdir():
            try:
                if file_path.is_file():
                    mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if mtime < cutoff:
                        file_path.unlink()
                        logger.info(f"Cleaned up stale file: {file_path.name}")
            except Exception as e:
                logger.warning(f"Could not clean up {file_path}: {e}")


# ─── Application Factory ──────────────────────────────────────

def create_application() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    app = FastAPI(
        title=settings.APP_NAME,
        description="Secure API for processing encrypted MPesa PDF statements",
        version="1.0.0",
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        openapi_url="/openapi.json" if settings.DEBUG else None,
        lifespan=lifespan,
    )
    
    # ─── Add Middleware (order matters - last added = first executed) ───
    
    # Compression
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    
    # Request size limit
    app.add_middleware(
        RequestSizeLimitMiddleware, 
        max_size_mb=settings.MAX_FILE_SIZE_MB + 1
    )
    
    # Security headers
    app.add_middleware(SecurityHeadersMiddleware)
    
    # Audit logging
    if not settings.DEBUG:
        app.add_middleware(AuditLogMiddleware)
    
    # Rate limiting
    app.add_middleware(
        RateLimitMiddleware,
        max_requests=settings.RATE_LIMIT_PER_MINUTE,
        window_seconds=60
    )
    
    # Request logging
    app.add_middleware(RequestLoggingMiddleware)
    
    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "X-Process-Time"],
        max_age=600,
    )
    
    # Trusted hosts (production)
    if not settings.DEBUG:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.ALLOWED_HOSTS,
        )
    
    # ─── Exception Handlers ───────────────────────────────────────
    
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, 
        exc: StarletteHTTPException
    ) -> JSONResponse:
        """Handle HTTP exceptions with consistent format."""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.detail if isinstance(exc.detail, str) else "Error",
                "status_code": exc.status_code,
            }
        )
    
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, 
        exc: RequestValidationError
    ) -> JSONResponse:
        """Handle validation errors without exposing internal details."""
        logger.warning(f"Validation error: {exc.errors()}")
        
        # Sanitize error messages
        errors = []
        for error in exc.errors():
            field = ".".join(str(loc) for loc in error.get("loc", []))
            errors.append(f"Invalid value for {field}")
        
        return JSONResponse(
            status_code=422,
            content={
                "error": "Validation Error",
                "detail": errors[:5],  # Limit number of errors shown
            }
        )
    
    @app.exception_handler(Exception)
    async def global_exception_handler(
        request: Request, 
        exc: Exception
    ) -> JSONResponse:
        """
        Global exception handler - never expose internal details.
        """
        # Log the full exception internally
        logger.exception(f"Unhandled exception: {type(exc).__name__}")
        
        # Return generic error to client
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal Server Error",
                "detail": "An unexpected error occurred. Please try again later.",
            }
        )
    
    # ─── Include Routers ──────────────────────────────────────────
    
    app.include_router(router)
    
    # ─── Root Endpoint ────────────────────────────────────────────
    
    @app.get("/", include_in_schema=False)
    async def root():
        """Root endpoint redirect."""
        return {
            "message": "MPesa Statement Processor API",
            "docs": "/docs" if settings.DEBUG else "Disabled in production",
            "health": "/api/v1/health"
        }
    
    return app


# Create application instance
app = create_application()


# ─── Development Server ───────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="debug" if settings.DEBUG else "info",
        access_log=settings.DEBUG,
    )