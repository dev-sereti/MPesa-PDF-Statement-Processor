# backend/app/services/file_manager.py
import os
import asyncio
import hashlib
import logging
import secrets
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass, field
import aiofiles
import aiofiles.os

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class FileInfo:
    """Metadata about a stored file."""
    file_id: str
    original_name: str
    safe_name: str
    file_path: Path
    file_hash: str
    size_bytes: int
    content_type: str
    created_at: datetime
    expires_at: datetime
    is_encrypted: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class SecureFileManager:
    """
    Manages secure file storage with automatic cleanup.
    
    Features:
    - Secure filename generation
    - File integrity verification
    - Automatic expiration and cleanup
    - Memory-efficient file handling
    """
    
    ALLOWED_EXTENSIONS = {'.pdf'}
    ALLOWED_CONTENT_TYPES = {'application/pdf', 'application/x-pdf'}
    CHUNK_SIZE = 8192  # 8KB chunks for reading
    
    def __init__(
        self,
        upload_dir: Path = None,
        output_dir: Path = None,
        max_file_size_mb: int = None,
        retention_minutes: int = None,
    ):
        self.upload_dir = upload_dir or settings.UPLOAD_DIR
        self.output_dir = output_dir or settings.OUTPUT_DIR
        self.max_file_size = (max_file_size_mb or settings.MAX_FILE_SIZE_MB) * 1024 * 1024
        self.retention_minutes = retention_minutes or settings.FILE_RETENTION_MINUTES
        
        self._files: Dict[str, FileInfo] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        
        # Ensure directories exist
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"FileManager initialized: upload={self.upload_dir}, output={self.output_dir}")
    
    async def store_upload(
        self,
        content: bytes,
        original_filename: str,
        content_type: str = "application/pdf",
        is_encrypted: bool = False,
        metadata: Dict[str, Any] = None,
    ) -> FileInfo:
        """
        Store an uploaded file securely.
        
        Args:
            content: File content as bytes
            original_filename: Original filename from upload
            content_type: MIME type
            is_encrypted: Whether PDF is password-protected
            metadata: Additional metadata to store
            
        Returns:
            FileInfo object with file details
            
        Raises:
            ValueError: If file validation fails
        """
        # Validate file
        self._validate_file(content, original_filename, content_type)
        
        # Generate secure file ID and path
        file_id = self._generate_file_id()
        safe_name = self._sanitize_filename(original_filename)
        file_path = self.upload_dir / f"{file_id}_{safe_name}"
        
        # Calculate hash before writing
        file_hash = self._calculate_hash(content)
        
        # Write file asynchronously
        try:
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(content)
            
            # Set restrictive permissions (owner read/write only)
            os.chmod(file_path, 0o600)
            
        except Exception as e:
            logger.error(f"Failed to write file {file_id}: {e}")
            # Clean up partial file
            if file_path.exists():
                file_path.unlink()
            raise
        
        # Create file info
        now = datetime.utcnow()
        file_info = FileInfo(
            file_id=file_id,
            original_name=original_filename,
            safe_name=safe_name,
            file_path=file_path,
            file_hash=file_hash,
            size_bytes=len(content),
            content_type=content_type,
            created_at=now,
            expires_at=now + timedelta(minutes=self.retention_minutes),
            is_encrypted=is_encrypted,
            metadata=metadata or {},
        )
        
        self._files[file_id] = file_info
        
        logger.info(
            f"File stored: id={file_id}, size={len(content)}, "
            f"encrypted={is_encrypted}, expires={file_info.expires_at}"
        )
        
        return file_info
    
    async def store_output(
        self,
        content: bytes,
        filename: str,
        related_file_id: str = None,
    ) -> FileInfo:
        """
        Store an output file (e.g., generated Excel).
        
        Args:
            content: File content
            filename: Output filename
            related_file_id: ID of related input file
            
        Returns:
            FileInfo for the output file
        """
        file_id = self._generate_file_id()
        safe_name = self._sanitize_filename(filename)
        file_path = self.output_dir / f"{file_id}_{safe_name}"
        
        try:
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(content)
            
            os.chmod(file_path, 0o600)
            
        except Exception as e:
            logger.error(f"Failed to write output file {file_id}: {e}")
            if file_path.exists():
                file_path.unlink()
            raise
        
        now = datetime.utcnow()
        file_info = FileInfo(
            file_id=file_id,
            original_name=filename,
            safe_name=safe_name,
            file_path=file_path,
            file_hash=self._calculate_hash(content),
            size_bytes=len(content),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            created_at=now,
            expires_at=now + timedelta(minutes=self.retention_minutes),
            metadata={"related_file_id": related_file_id} if related_file_id else {},
        )
        
        self._files[file_id] = file_info
        
        logger.info(f"Output file stored: id={file_id}, size={len(content)}")
        
        return file_info
    
    async def get_file_content(self, file_id: str) -> Optional[bytes]:
        """
        Retrieve file content by ID.
        
        Args:
            file_id: The file identifier
            
        Returns:
            File content as bytes, or None if not found/expired
        """
        file_info = self._files.get(file_id)
        
        if not file_info:
            logger.warning(f"File not found: {file_id}")
            return None
        
        if datetime.utcnow() > file_info.expires_at:
            logger.warning(f"File expired: {file_id}")
            await self.delete_file(file_id)
            return None
        
        if not file_info.file_path.exists():
            logger.warning(f"File missing from disk: {file_id}")
            del self._files[file_id]
            return None
        
        try:
            async with aiofiles.open(file_info.file_path, 'rb') as f:
                content = await f.read()
            
            # Verify integrity
            if self._calculate_hash(content) != file_info.file_hash:
                logger.error(f"File integrity check failed: {file_id}")
                await self.delete_file(file_id)
                return None
            
            return content
            
        except Exception as e:
            logger.error(f"Failed to read file {file_id}: {e}")
            return None
    
    async def get_file_path(self, file_id: str) -> Optional[Path]:
        """Get file path for direct file serving."""
        file_info = self._files.get(file_id)
        
        if not file_info:
            return None
        
        if datetime.utcnow() > file_info.expires_at:
            await self.delete_file(file_id)
            return None
        
        if not file_info.file_path.exists():
            del self._files[file_id]
            return None
        
        return file_info.file_path
    
    def get_file_info(self, file_id: str) -> Optional[FileInfo]:
        """Get file metadata without reading content."""
        file_info = self._files.get(file_id)
        
        if file_info and datetime.utcnow() > file_info.expires_at:
            return None
        
        return file_info
    
    async def delete_file(self, file_id: str) -> bool:
        """
        Securely delete a file.
        
        Args:
            file_id: The file identifier
            
        Returns:
            True if deleted, False if not found
        """
        file_info = self._files.pop(file_id, None)
        
        if not file_info:
            return False
        
        try:
            if file_info.file_path.exists():
                # Overwrite with zeros before deletion (secure delete)
                await self._secure_delete(file_info.file_path)
                logger.info(f"File securely deleted: {file_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete file {file_id}: {e}")
            return False
    
    async def cleanup_expired(self) -> int:
        """
        Remove all expired files.
        
        Returns:
            Number of files cleaned up
        """
        now = datetime.utcnow()
        expired_ids = [
            file_id for file_id, info in self._files.items()
            if now > info.expires_at
        ]
        
        count = 0
        for file_id in expired_ids:
            if await self.delete_file(file_id):
                count += 1
        
        if count > 0:
            logger.info(f"Cleaned up {count} expired files")
        
        return count
    
    async def cleanup_all(self) -> int:
        """Remove all managed files."""
        file_ids = list(self._files.keys())
        count = 0
        
        for file_id in file_ids:
            if await self.delete_file(file_id):
                count += 1
        
        # Also clean up any orphaned files in directories
        for directory in [self.upload_dir, self.output_dir]:
            for file_path in directory.iterdir():
                if file_path.is_file():
                    try:
                        await self._secure_delete(file_path)
                        count += 1
                    except Exception as e:
                        logger.warning(f"Could not delete orphan file {file_path}: {e}")
        
        logger.info(f"Cleaned up {count} total files")
        return count
    
    def start_cleanup_task(self, interval_minutes: int = 5) -> None:
        """Start background cleanup task."""
        async def cleanup_loop():
            while True:
                await asyncio.sleep(interval_minutes * 60)
                try:
                    await self.cleanup_expired()
                except Exception as e:
                    logger.error(f"Cleanup task error: {e}")
        
        self._cleanup_task = asyncio.create_task(cleanup_loop())
        logger.info(f"Started cleanup task with {interval_minutes}min interval")
    
    def stop_cleanup_task(self) -> None:
        """Stop background cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None
    
    # ─── Private Methods ──────────────────────────────────────────
    
    def _validate_file(
        self, 
        content: bytes, 
        filename: str, 
        content_type: str
    ) -> None:
        """Validate file before storage."""
        # Size check
        if len(content) > self.max_file_size:
            raise ValueError(
                f"File too large: {len(content)} bytes "
                f"(max: {self.max_file_size} bytes)"
            )
        
        if len(content) < 100:
            raise ValueError("File too small to be valid")
        
        # Extension check
        ext = Path(filename).suffix.lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            raise ValueError(f"Invalid file extension: {ext}")
        
        # Content type check
        if content_type and content_type not in self.ALLOWED_CONTENT_TYPES:
            # Allow empty content type
            if content_type:
                logger.warning(f"Unexpected content type: {content_type}")
        
        # Magic bytes check for PDF
        if not content.startswith(b'%PDF'):
            raise ValueError("File is not a valid PDF")
    
    def _generate_file_id(self) -> str:
        """Generate a cryptographically secure file ID."""
        return secrets.token_urlsafe(16)
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename to prevent path traversal and other attacks."""
        import re
        
        # Get just the filename, not any path
        filename = Path(filename).name
        
        # Remove any non-alphanumeric characters except dots, hyphens, underscores
        safe = re.sub(r'[^\w\-_\.]', '_', filename)
        
        # Remove leading dots (hidden files) and multiple dots
        safe = re.sub(r'^\.+', '', safe)
        safe = re.sub(r'\.+', '.', safe)
        
        # Limit length
        if len(safe) > 100:
            name, ext = os.path.splitext(safe)
            safe = name[:95] + ext
        
        return safe if safe else "unnamed_file.pdf"
    
    def _calculate_hash(self, content: bytes) -> str:
        """Calculate SHA-256 hash of content."""
        return hashlib.sha256(content).hexdigest()
    
    async def _secure_delete(self, file_path: Path) -> None:
        """Securely delete a file by overwriting before unlinking."""
        try:
            if file_path.exists():
                size = file_path.stat().st_size
                
                # Overwrite with random data (for sensitive files)
                async with aiofiles.open(file_path, 'wb') as f:
                    await f.write(os.urandom(min(size, 1024 * 1024)))
                
                # Delete the file
                await aiofiles.os.remove(file_path)
                
        except Exception as e:
            # Fall back to regular delete
            logger.warning(f"Secure delete failed, using regular delete: {e}")
            if file_path.exists():
                file_path.unlink()


# Singleton instance
file_manager = SecureFileManager()