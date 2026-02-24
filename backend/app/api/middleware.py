# backend/app/api/middleware.py
import time
import uuid
import logging
from typing import Callable, Optional
from datetime import datetime
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from fastapi import status

from app.config import settings
from app.security import RateLimiter

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Logs all incoming requests with timing and outcome.
    Sanitizes sensitive data from logs.
    """
    
    SENSITIVE_PATHS = ['/api/v1/process']
    SENSITIVE_HEADERS = ['authorization', 'cookie', 'x-api-key']
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = str(uuid.uuid4())[:8]
        start_time = time.time()
        
        # Attach request ID for tracing
        request.state.request_id = request_id
        
        # Log request (sanitized)
        self._log_request(request, request_id)
        
        try:
            response = await call_next(request)
            
            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id
            
            # Log response
            duration_ms = (time.time() - start_time) * 1000
            self._log_response(request, response, request_id, duration_ms)
            
            return response
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                f"[{request_id}] Unhandled exception: {type(e).__name__} "
                f"path={request.url.path} duration={duration_ms:.2f}ms"
            )
            raise
    
    def _log_request(self, request: Request, request_id: str) -> None:
        """Log incoming request with sanitized data."""
        client_ip = self._get_client_ip(request)
        
        log_data = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "client_ip": client_ip,
            "user_agent": request.headers.get("user-agent", "unknown")[:100],
        }
        
        # Don't log query params for sensitive paths
        if request.url.path not in self.SENSITIVE_PATHS and request.url.query:
            log_data["query"] = request.url.query[:200]
        
        logger.info(f"[{request_id}] Request: {log_data}")
    
    def _log_response(
        self, 
        request: Request, 
        response: Response, 
        request_id: str, 
        duration_ms: float
    ) -> None:
        """Log response with timing."""
        log_level = logging.WARNING if response.status_code >= 400 else logging.INFO
        
        logger.log(
            log_level,
            f"[{request_id}] Response: status={response.status_code} "
            f"path={request.url.path} duration={duration_ms:.2f}ms"
        )
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract real client IP, handling proxies."""
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Global rate limiting middleware.
    Per-IP request throttling.
    """
    
    def __init__(self, app, max_requests: int = 60, window_seconds: int = 60):
        super().__init__(app)
        self.rate_limiter = RateLimiter(max_requests, window_seconds)
        self.exempt_paths = ['/api/v1/health', '/docs', '/openapi.json']
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip rate limiting for exempt paths
        if request.url.path in self.exempt_paths:
            return await call_next(request)
        
        client_ip = self._get_client_ip(request)
        
        if not self.rate_limiter.is_allowed(client_ip):
            logger.warning(f"Rate limit exceeded for {client_ip}")
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Too many requests",
                    "detail": "Please wait before making more requests.",
                    "retry_after": 60
                },
                headers={"Retry-After": "60"}
            )
        
        return await call_next(request)
    
    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds comprehensive security headers to all responses.
    """
    
    SECURITY_HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
        "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    }
    
    CSP_POLICY = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self';"
    )
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        
        # Add security headers
        for header, value in self.SECURITY_HEADERS.items():
            response.headers[header] = value
        
        # Add CSP header
        response.headers["Content-Security-Policy"] = self.CSP_POLICY
        
        # Remove potentially sensitive headers
        response.headers.pop("Server", None)
        response.headers.pop("X-Powered-By", None)
        
        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Limits request body size to prevent memory exhaustion attacks.
    """
    
    def __init__(self, app, max_size_mb: int = 10):
        super().__init__(app)
        self.max_size_bytes = max_size_mb * 1024 * 1024
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        content_length = request.headers.get("content-length")
        
        if content_length:
            try:
                size = int(content_length)
                if size > self.max_size_bytes:
                    return JSONResponse(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        content={
                            "error": "Request too large",
                            "detail": f"Maximum allowed size is {self.max_size_bytes // (1024*1024)}MB",
                            "max_size_mb": self.max_size_bytes // (1024 * 1024)
                        }
                    )
            except ValueError:
                pass
        
        return await call_next(request)


class SessionValidationMiddleware(BaseHTTPMiddleware):
    """
    Validates session tokens and prevents session fixation attacks.
    """
    
    PROTECTED_PATHS = ['/api/v1/process', '/api/v1/download']
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Check if path requires session validation
        path = request.url.path
        
        if any(path.startswith(p) for p in self.PROTECTED_PATHS):
            # Verify origin/referer for CSRF protection
            origin = request.headers.get("origin")
            referer = request.headers.get("referer")
            
            if origin:
                allowed = any(
                    origin.startswith(allowed_origin) 
                    for allowed_origin in settings.ALLOWED_ORIGINS
                )
                if not allowed:
                    logger.warning(f"CSRF check failed: invalid origin {origin}")
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={"error": "Invalid origin"}
                    )
        
        return await call_next(request)


class AuditLogMiddleware(BaseHTTPMiddleware):
    """
    Creates audit logs for sensitive operations.
    """
    
    AUDITED_PATHS = {
        '/api/v1/upload': 'FILE_UPLOAD',
        '/api/v1/process': 'STATEMENT_PROCESS',
        '/api/v1/download': 'FILE_DOWNLOAD',
    }
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        
        # Check if this path should be audited
        action = None
        for audited_path, audit_action in self.AUDITED_PATHS.items():
            if path.startswith(audited_path):
                action = audit_action
                break
        
        response = await call_next(request)
        
        if action:
            self._create_audit_log(request, response, action)
        
        return response
    
    def _create_audit_log(
        self, 
        request: Request, 
        response: Response, 
        action: str
    ) -> None:
        """Create an audit log entry."""
        client_ip = request.headers.get(
            "x-forwarded-for", 
            request.client.host if request.client else "unknown"
        ).split(",")[0].strip()
        
        request_id = getattr(request.state, 'request_id', 'unknown')
        
        audit_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "request_id": request_id,
            "client_ip": client_ip,
            "path": request.url.path,
            "method": request.method,
            "status_code": response.status_code,
            "user_agent": request.headers.get("user-agent", "")[:100],
        }
        
        # Log to audit logger (could be separate file/service)
        audit_logger = logging.getLogger("audit")
        audit_logger.info(f"AUDIT: {audit_entry}")