# backend/app/utils/helpers.py
import re
import hashlib
import secrets
import string
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from decimal import Decimal, InvalidOperation
import logging

logger = logging.getLogger(__name__)


# ─── String Utilities ─────────────────────────────────────────

def truncate(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate text to max length with suffix."""
    if not text or len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def mask_sensitive(value: str, visible_chars: int = 4) -> str:
    """
    Mask sensitive string, showing only last N characters.
    Example: "1234567890" -> "******7890"
    """
    if not value:
        return ""
    
    if len(value) <= visible_chars:
        return "*" * len(value)
    
    return "*" * (len(value) - visible_chars) + value[-visible_chars:]


def mask_phone_number(phone: str) -> str:
    """
    Mask phone number for display.
    Example: "+254712345678" -> "+254****5678"
    """
    if not phone:
        return ""
    
    # Remove non-digit characters for processing
    digits = re.sub(r'\D', '', phone)
    
    if len(digits) < 8:
        return mask_sensitive(phone)
    
    # Show first 4 and last 4 digits
    prefix = phone[:phone.index(digits[0]) + 4] if '+' in phone else digits[:4]
    suffix = digits[-4:]
    masked_middle = '*' * (len(digits) - 8)
    
    return f"{prefix}{masked_middle}{suffix}"


def clean_whitespace(text: str) -> str:
    """Normalize whitespace in text."""
    if not text:
        return ""
    # Replace multiple spaces/tabs/newlines with single space
    return re.sub(r'\s+', ' ', text).strip()


# ─── Amount Parsing ───────────────────────────────────────────

def parse_amount(amount_str: str) -> Optional[Decimal]:
    """
    Parse monetary amount from various formats.
    
    Examples:
        "KES 1,234.56" -> Decimal("1234.56")
        "Ksh. 1,000" -> Decimal("1000")
        "1234.56" -> Decimal("1234.56")
    """
    if not amount_str:
        return None
    
    try:
        # Remove currency symbols and text
        cleaned = re.sub(r'(?i)(ksh\.?|kes|ksh|/=)', '', str(amount_str))
        
        # Remove whitespace
        cleaned = cleaned.strip()
        
        # Remove thousand separators (commas)
        cleaned = cleaned.replace(',', '')
        
        # Handle negative amounts
        is_negative = cleaned.startswith('-') or cleaned.startswith('(')
        cleaned = cleaned.strip('-() ')
        
        if not cleaned or cleaned == '-':
            return None
        
        # Parse to Decimal
        amount = Decimal(cleaned)
        
        return -amount if is_negative else amount
        
    except (InvalidOperation, ValueError) as e:
        logger.debug(f"Could not parse amount '{amount_str}': {e}")
        return None


def format_amount(amount: Decimal, currency: str = "KES") -> str:
    """Format amount for display."""
    if amount is None:
        return ""
    
    formatted = f"{currency} {amount:,.2f}"
    return formatted


# ─── Date Parsing ─────────────────────────────────────────────

DATE_FORMATS = [
    "%d/%m/%Y %I:%M %p",      # 01/12/2024 10:30 AM
    "%d/%m/%Y %H:%M:%S",      # 01/12/2024 10:30:00
    "%d/%m/%Y %H:%M",         # 01/12/2024 10:30
    "%d/%m/%Y",               # 01/12/2024
    "%Y-%m-%d %H:%M:%S",      # 2024-12-01 10:30:00
    "%Y-%m-%d",               # 2024-12-01
    "%d-%m-%Y %H:%M:%S",      # 01-12-2024 10:30:00
    "%d %B %Y %I:%M %p",      # 01 December 2024 10:30 AM
    "%d %b %Y %I:%M %p",      # 01 Dec 2024 10:30 AM
    "%d %b %Y",               # 01 Dec 2024
]


def parse_date(date_str: str) -> Optional[datetime]:
    """
    Parse date string with multiple format support.
    
    Args:
        date_str: Date string in various formats
        
    Returns:
        datetime object or None if parsing fails
    """
    if not date_str:
        return None
    
    # Normalize the string
    normalized = clean_whitespace(date_str)
    
    # Normalize AM/PM spacing
    normalized = re.sub(r'(\d)([AP]M)', r'\1 \2', normalized, flags=re.IGNORECASE)
    
    # Try each format
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    
    # Try dateutil as fallback
    try:
        from dateutil import parser as dateutil_parser
        return dateutil_parser.parse(normalized, dayfirst=True)
    except Exception:
        pass
    
    logger.debug(f"Could not parse date: '{date_str}'")
    return None


def format_date(dt: datetime, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format datetime for display."""
    if not dt:
        return ""
    return dt.strftime(format_str)


def format_relative_time(dt: datetime) -> str:
    """Format datetime as relative time (e.g., '5 minutes ago')."""
    if not dt:
        return ""
    
    now = datetime.utcnow()
    diff = now - dt
    
    if diff < timedelta(minutes=1):
        return "just now"
    elif diff < timedelta(hours=1):
        mins = int(diff.total_seconds() / 60)
        return f"{mins} minute{'s' if mins != 1 else ''} ago"
    elif diff < timedelta(days=1):
        hours = int(diff.total_seconds() / 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif diff < timedelta(days=30):
        days = diff.days
        return f"{days} day{'s' if days != 1 else ''} ago"
    else:
        return dt.strftime("%Y-%m-%d")


# ─── ID Generation ────────────────────────────────────────────

def generate_session_id(length: int = 32) -> str:
    """Generate a cryptographically secure session ID."""
    return secrets.token_urlsafe(length)


def generate_download_token() -> str:
    """Generate a secure download token."""
    return secrets.token_urlsafe(24)


def generate_short_id(length: int = 8) -> str:
    """Generate a short random ID for display purposes."""
    alphabet = string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


# ─── Hash Utilities ───────────────────────────────────────────

def hash_content(content: bytes) -> str:
    """Generate SHA-256 hash of content."""
    return hashlib.sha256(content).hexdigest()


def hash_string(text: str) -> str:
    """Generate SHA-256 hash of string."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def verify_hash(content: bytes, expected_hash: str) -> bool:
    """Verify content against expected hash."""
    actual_hash = hash_content(content)
    # Use constant-time comparison to prevent timing attacks
    return secrets.compare_digest(actual_hash, expected_hash)


# ─── Data Extraction Helpers ──────────────────────────────────

def extract_phone_number(text: str) -> Optional[str]:
    """
    Extract Kenyan phone number from text.
    
    Returns normalized format: +254XXXXXXXXX
    """
    if not text:
        return None
    
    patterns = [
        r'\+254(\d{9})',        # +254712345678
        r'254(\d{9})',          # 254712345678
        r'0([17]\d{8})',        # 0712345678
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return f"+254{match.group(1)}"
    
    return None


def extract_receipt_number(text: str) -> Optional[str]:
    """
    Extract MPesa receipt number from text.
    
    MPesa receipts follow pattern: XXX0000000 (2-3 letters + 7-10 digits)
    """
    if not text:
        return None
    
    pattern = r'\b([A-Z]{2,3}\d{7,10})\b'
    match = re.search(pattern, text.upper())
    
    return match.group(1) if match else None


def extract_all_amounts(text: str) -> List[Decimal]:
    """Extract all monetary amounts from text."""
    if not text:
        return []
    
    pattern = r'(?:Ksh\.?|KES)?\s*([\d,]+\.?\d{0,2})'
    matches = re.findall(pattern, text, re.IGNORECASE)
    
    amounts = []
    for match in matches:
        parsed = parse_amount(match)
        if parsed is not None and parsed > 0:
            amounts.append(parsed)
    
    return amounts


# ─── Statistics Helpers ───────────────────────────────────────

def calculate_statistics(amounts: List[Decimal]) -> Dict[str, Any]:
    """Calculate basic statistics for a list of amounts."""
    if not amounts:
        return {
            "count": 0,
            "sum": Decimal("0"),
            "mean": Decimal("0"),
            "min": Decimal("0"),
            "max": Decimal("0"),
        }
    
    total = sum(amounts)
    count = len(amounts)
    
    return {
        "count": count,
        "sum": total,
        "mean": total / count,
        "min": min(amounts),
        "max": max(amounts),
    }


def group_by_date(
    items: List[Tuple[datetime, Any]], 
    granularity: str = "day"
) -> Dict[str, List[Any]]:
    """
    Group items by date.
    
    Args:
        items: List of (datetime, value) tuples
        granularity: 'day', 'week', 'month', or 'year'
        
    Returns:
        Dictionary with date keys and lists of values
    """
    format_map = {
        "day": "%Y-%m-%d",
        "week": "%Y-W%W",
        "month": "%Y-%m",
        "year": "%Y",
    }
    
    date_format = format_map.get(granularity, "%Y-%m-%d")
    grouped = {}
    
    for dt, value in items:
        if dt:
            key = dt.strftime(date_format)
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(value)
    
    return grouped


# ─── Error Handling Helpers ───────────────────────────────────

def safe_get(dictionary: dict, *keys, default=None):
    """Safely get nested dictionary values."""
    result = dictionary
    for key in keys:
        try:
            result = result[key]
        except (KeyError, TypeError, IndexError):
            return default
    return result


def retry_operation(
    operation,
    max_attempts: int = 3,
    delay_seconds: float = 1.0,
    exceptions: tuple = (Exception,)
) -> Any:
    """
    Retry an operation with exponential backoff.
    
    Args:
        operation: Callable to execute
        max_attempts: Maximum number of attempts
        delay_seconds: Initial delay between attempts
        exceptions: Tuple of exceptions to catch
        
    Returns:
        Result of the operation
        
    Raises:
        The last exception if all attempts fail
    """
    import time
    
    last_exception = None
    
    for attempt in range(max_attempts):
        try:
            return operation()
        except exceptions as e:
            last_exception = e
            if attempt < max_attempts - 1:
                sleep_time = delay_seconds * (2 ** attempt)
                time.sleep(sleep_time)
    
    raise last_exception