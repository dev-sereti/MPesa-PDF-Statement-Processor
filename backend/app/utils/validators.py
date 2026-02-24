# backend/app/utils/validators.py
import re
import logging
from typing import Tuple, Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)


class PDFValidator:
    """Validates PDF files for security and format compliance."""
    
    # PDF magic bytes
    PDF_MAGIC = b'%PDF-'
    
    # Suspicious patterns that might indicate malicious content
    SUSPICIOUS_PATTERNS = [
        b'/JavaScript',
        b'/JS',
        b'/Launch',
        b'/EmbeddedFile',
        b'/OpenAction',
        b'/AA',  # Additional Actions
        b'/URI',
        b'eval(',
    ]
    
    # Maximum nesting depth to prevent zip bomb style attacks
    MAX_OBJECT_DEPTH = 100
    
    @classmethod
    def validate(
        cls, 
        content: bytes, 
        filename: str = None
    ) -> Tuple[bool, str, dict]:
        """
        Comprehensive PDF validation.
        
        Args:
            content: PDF file content
            filename: Original filename for extension check
            
        Returns:
            Tuple of (is_valid, message, metadata)
        """
        metadata = {
            "size_bytes": len(content),
            "has_suspicious_content": False,
            "is_encrypted": False,
            "pdf_version": None,
        }
        
        # Basic size checks
        if len(content) < 100:
            return False, "File is too small to be a valid PDF", metadata
        
        if len(content) > 50 * 1024 * 1024:  # 50MB absolute max
            return False, "File exceeds maximum allowed size", metadata
        
        # Magic bytes check
        if not content.startswith(cls.PDF_MAGIC):
            return False, "File does not have valid PDF header", metadata
        
        # Extract PDF version
        version_match = re.search(rb'%PDF-(\d\.\d)', content[:20])
        if version_match:
            metadata["pdf_version"] = version_match.group(1).decode('ascii')
        
        # Check for PDF trailer
        if b'%%EOF' not in content[-1024:]:
            return False, "PDF file appears to be truncated", metadata
        
        # Check filename extension if provided
        if filename:
            ext = Path(filename).suffix.lower()
            if ext != '.pdf':
                return False, f"Invalid file extension: {ext}", metadata
        
        # Check for suspicious JavaScript/actions (basic check)
        for pattern in cls.SUSPICIOUS_PATTERNS:
            if pattern in content:
                metadata["has_suspicious_content"] = True
                logger.warning(f"Suspicious pattern found in PDF: {pattern}")
                # We still allow it but flag it
                break
        
        # Check for encryption marker
        if b'/Encrypt' in content:
            metadata["is_encrypted"] = True
        
        return True, "Valid PDF file", metadata


class PINValidator:
    """Validates MPesa statement PINs."""
    
    # MPesa PINs are typically numeric, 4-12 digits
    # Some statements use phone numbers as PINs
    
    MIN_LENGTH = 4
    MAX_LENGTH = 20
    
    # Patterns that are valid PINs
    VALID_PATTERNS = [
        r'^\d{4,12}$',  # Simple numeric PIN
        r'^\+?254\d{9}$',  # Kenyan phone number
        r'^0[17]\d{8}$',  # Local phone number format
    ]
    
    @classmethod
    def validate(cls, pin: str) -> Tuple[bool, str]:
        """
        Validate PIN format without logging the actual PIN.
        
        Args:
            pin: The PIN to validate
            
        Returns:
            Tuple of (is_valid, message)
        """
        if not pin:
            return False, "PIN is required"
        
        pin = pin.strip()
        
        # Length check
        if len(pin) < cls.MIN_LENGTH:
            return False, f"PIN must be at least {cls.MIN_LENGTH} characters"
        
        if len(pin) > cls.MAX_LENGTH:
            return False, f"PIN cannot exceed {cls.MAX_LENGTH} characters"
        
        # Check against valid patterns
        for pattern in cls.VALID_PATTERNS:
            if re.match(pattern, pin):
                return True, "Valid PIN format"
        
        # Allow alphanumeric for edge cases
        if re.match(r'^[\w\d]+$', pin):
            return True, "Valid PIN format"
        
        return False, "Invalid PIN format"
    
    @classmethod
    def sanitize(cls, pin: str) -> str:
        """
        Sanitize PIN input.
        Removes whitespace and common formatting characters.
        """
        if not pin:
            return ""
        
        # Remove spaces, dashes, parentheses
        sanitized = re.sub(r'[\s\-\(\)]', '', pin)
        
        return sanitized[:cls.MAX_LENGTH]


class SessionIDValidator:
    """Validates session IDs."""
    
    # Session IDs should be URL-safe base64
    PATTERN = re.compile(r'^[A-Za-z0-9_\-]{20,64}$')
    
    @classmethod
    def validate(cls, session_id: str) -> Tuple[bool, str]:
        """
        Validate session ID format.
        
        Args:
            session_id: The session ID to validate
            
        Returns:
            Tuple of (is_valid, message)
        """
        if not session_id:
            return False, "Session ID is required"
        
        if not cls.PATTERN.match(session_id):
            return False, "Invalid session ID format"
        
        return True, "Valid session ID"


class InputSanitizer:
    """Sanitizes user inputs to prevent injection attacks."""
    
    # Characters to remove from most inputs
    DANGEROUS_CHARS = re.compile(r'[<>&\'"\\;`]')
    
    # Null bytes and control characters
    CONTROL_CHARS = re.compile(r'[\x00-\x1f\x7f-\x9f]')
    
    @classmethod
    def sanitize_string(
        cls, 
        value: str, 
        max_length: int = 1000,
        allow_newlines: bool = False
    ) -> str:
        """
        Sanitize a string input.
        
        Args:
            value: The string to sanitize
            max_length: Maximum allowed length
            allow_newlines: Whether to preserve newlines
            
        Returns:
            Sanitized string
        """
        if not value:
            return ""
        
        # Remove control characters
        result = cls.CONTROL_CHARS.sub('', value)
        
        # Remove or escape dangerous characters
        result = cls.DANGEROUS_CHARS.sub('', result)
        
        # Handle newlines
        if not allow_newlines:
            result = result.replace('\n', ' ').replace('\r', ' ')
        
        # Collapse multiple spaces
        result = re.sub(r' +', ' ', result)
        
        # Trim and limit length
        result = result.strip()[:max_length]
        
        return result
    
    @classmethod
    def sanitize_filename(cls, filename: str) -> str:
        """
        Sanitize a filename to prevent path traversal.
        
        Args:
            filename: The filename to sanitize
            
        Returns:
            Safe filename
        """
        if not filename:
            return "unnamed_file"
        
        # Get just the filename part
        filename = Path(filename).name
        
        # Remove path separators and null bytes
        filename = filename.replace('/', '_').replace('\\', '_')
        filename = filename.replace('\x00', '')
        
        # Remove leading dots
        filename = filename.lstrip('.')
        
        # Keep only safe characters
        safe = re.sub(r'[^\w\-_\.]', '_', filename)
        
        # Collapse multiple underscores
        safe = re.sub(r'_+', '_', safe)
        
        # Limit length
        if len(safe) > 100:
            name, ext = Path(safe).stem, Path(safe).suffix
            safe = name[:95] + ext
        
        return safe if safe else "unnamed_file"


def validate_request_data(
    session_id: str = None,
    pin: str = None,
    filename: str = None,
) -> Tuple[bool, List[str]]:
    """
    Validate common request parameters.
    
    Returns:
        Tuple of (all_valid, list_of_errors)
    """
    errors = []
    
    if session_id is not None:
        valid, msg = SessionIDValidator.validate(session_id)
        if not valid:
            errors.append(f"Session ID: {msg}")
    
    if pin is not None:
        valid, msg = PINValidator.validate(pin)
        if not valid:
            errors.append(f"PIN: {msg}")
    
    if filename is not None:
        sanitized = InputSanitizer.sanitize_filename(filename)
        if sanitized != filename and 'unnamed' not in sanitized:
            errors.append("Filename contains invalid characters")
    
    return len(errors) == 0, errors