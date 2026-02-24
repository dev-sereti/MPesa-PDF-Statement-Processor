# backend/app/security.py
import hashlib
import hmac
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

class RateLimiter:
    """Token bucket rate limiter with per-IP tracking."""
    
    def __init__(self, max_requests: int, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: Dict[str, list] = defaultdict(list)
    
    def is_allowed(self, identifier: str) -> bool:
        now = time.time()
        window_start = now - self.window_seconds
        
        # Clean old requests
        self._requests[identifier] = [
            req_time for req_time in self._requests[identifier]
            if req_time > window_start
        ]
        
        if len(self._requests[identifier]) >= self.max_requests:
            logger.warning(f"Rate limit exceeded for {identifier}")
            return False
        
        self._requests[identifier].append(now)
        return True


class PinAttemptTracker:
    """Track PIN attempts per session to prevent brute force."""
    
    def __init__(self, max_attempts: int = 3, lockout_minutes: int = 15):
        self.max_attempts = max_attempts
        self.lockout_duration = timedelta(minutes=lockout_minutes)
        self._attempts: Dict[str, dict] = {}
    
    def check_and_record(self, session_id: str, success: bool) -> dict:
        now = datetime.utcnow()
        
        if session_id not in self._attempts:
            self._attempts[session_id] = {"count": 0, "locked_until": None}
        
        record = self._attempts[session_id]
        
        # Check if locked out
        if record["locked_until"] and now < record["locked_until"]:
            remaining = (record["locked_until"] - now).seconds
            return {
                "allowed": False,
                "locked": True,
                "remaining_seconds": remaining,
                "attempts_left": 0
            }
        
        if success:
            # Reset on success
            self._attempts[session_id] = {"count": 0, "locked_until": None}
            return {"allowed": True, "locked": False, "attempts_left": self.max_attempts}
        
        # Failed attempt
        record["count"] += 1
        
        if record["count"] >= self.max_attempts:
            record["locked_until"] = now + self.lockout_duration
            logger.warning(f"Session {session_id[:8]}... locked after {self.max_attempts} failed attempts")
            return {
                "allowed": False,
                "locked": True,
                "remaining_seconds": self.lockout_duration.seconds,
                "attempts_left": 0
            }
        
        attempts_left = self.max_attempts - record["count"]
        return {
            "allowed": False,
            "locked": False,
            "attempts_left": attempts_left
        }
    
    def get_attempts_left(self, session_id: str) -> int:
        if session_id not in self._attempts:
            return self.max_attempts
        record = self._attempts[session_id]
        return max(0, self.max_attempts - record["count"])


def generate_session_id() -> str:
    """Generate a cryptographically secure session ID."""
    return secrets.token_urlsafe(32)


def secure_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal attacks."""
    import re
    # Keep only alphanumeric, dots, hyphens, underscores
    safe = re.sub(r'[^\w\-_\.]', '_', filename)
    # Prevent hidden files and path traversal
    safe = safe.lstrip('.')
    # Limit length
    return safe[:100] if safe else "unnamed_file"


def hash_file_content(content: bytes) -> str:
    """Create SHA-256 hash of file content for integrity checking."""
    return hashlib.sha256(content).hexdigest()