# backend/app/config.py
from pydantic_settings import BaseSettings
from pathlib import Path
import secrets

class Settings(BaseSettings):
    # Application
    APP_NAME: str = "MPesa Statement Processor"
    DEBUG: bool = False
    SECRET_KEY: str = secrets.token_urlsafe(32)
    
    # File handling
    MAX_FILE_SIZE_MB: int = 10
    UPLOAD_DIR: Path = Path("/tmp/mpesa_uploads")
    OUTPUT_DIR: Path = Path("/tmp/mpesa_outputs")
    FILE_RETENTION_MINUTES: int = 30  # Auto-delete files after 30 mins
    
    # Security
    MAX_PIN_ATTEMPTS: int = 3
    RATE_LIMIT_PER_MINUTE: int = 10
    ALLOWED_ORIGINS: list = ["http://localhost:3000"]
    
    # Session
    SESSION_EXPIRE_MINUTES: int = 30
    
    class Config:
        env_file = ".env"
        case_sensitive = True

    def __post_init__(self):
        self.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

settings = Settings()