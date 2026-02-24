# backend/app/models/schemas.py
from pydantic import BaseModel, validator, Field
from typing import Optional, List
from datetime import datetime
import re


class UploadResponse(BaseModel):
    session_id: str
    filename: str
    is_encrypted: bool
    file_size_kb: float
    message: str


class ProcessRequest(BaseModel):
    session_id: str = Field(..., min_length=10, max_length=100)
    pin: Optional[str] = Field(None, max_length=20)
    
    @validator('session_id')
    def validate_session_id(cls, v):
        if not re.match(r'^[A-Za-z0-9_\-]+$', v):
            raise ValueError('Invalid session ID format')
        return v
    
    @validator('pin')
    def validate_pin(cls, v):
        if v is not None:
            v = v.strip()
            if v and not re.match(r'^[\d\+\s\-]{4,20}$', v):
                raise ValueError('Invalid PIN format')
        return v


class ProcessResponse(BaseModel):
    success: bool
    download_token: Optional[str] = None
    transaction_count: int = 0
    parsing_warnings: List[str] = []
    statement_period: Optional[str] = None
    account_name: Optional[str] = None
    message: str


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str