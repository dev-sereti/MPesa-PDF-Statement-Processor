# backend/app/api/routes.py
import uuid
import logging
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import aiofiles

from fastapi import (
    APIRouter, UploadFile, File, Form, HTTPException,
    BackgroundTasks, Request, Response
)
from fastapi.responses import FileResponse, JSONResponse

from app.config import settings
from app.security import (
    RateLimiter, PinAttemptTracker, 
    generate_session_id, secure_filename, hash_file_content
)
from app.services.pdf_processor import SecurePDFProcessor
from app.services.statement_parser import MPesaStatementParser
from app.services.excel_generator import MPesaExcelGenerator
from app.models.schemas import (
    UploadResponse, ProcessRequest, ProcessResponse, 
    ErrorResponse, HealthResponse
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")

# Service instances
pdf_processor = SecurePDFProcessor()
parser = MPesaStatementParser()
excel_generator = MPesaExcelGenerator()

# Security instances
rate_limiter = RateLimiter(max_requests=settings.RATE_LIMIT_PER_MINUTE)
pin_tracker = PinAttemptTracker(max_attempts=settings.MAX_PIN_ATTEMPTS)

# In-memory session store (use Redis in production)
sessions: dict = {}


def get_client_ip(request: Request) -> str:
    """Extract real client IP handling proxies."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
        version="1.0.0"
    )


@router.post("/upload", response_model=UploadResponse)
async def upload_pdf(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    """
    Upload a PDF file for processing.
    Returns session ID for subsequent operations.
    """
    client_ip = get_client_ip(request)
    
    # Rate limiting
    if not rate_limiter.is_allowed(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please wait before trying again."
        )
    
    # Validate file type
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are accepted."
        )
    
    # Check content type
    if file.content_type and 'pdf' not in file.content_type.lower():
        raise HTTPException(
            status_code=400,
            detail="Invalid file content type."
        )
    
    # Read file content
    content = await file.read()
    
    # Size check
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {settings.MAX_FILE_SIZE_MB}MB."
        )
    
    if len(content) < 100:  # Too small to be a real PDF
        raise HTTPException(status_code=400, detail="File appears to be empty or corrupt.")
    
    # Validate PDF
    is_valid, message, is_encrypted = pdf_processor.validate_pdf(content)
    if not is_valid:
        raise HTTPException(status_code=400, detail=message)
    
    # Generate session
    session_id = generate_session_id()
    safe_name = secure_filename(file.filename)
    file_hash = hash_file_content(content)
    
    # Store in session (encrypted in production)
    sessions[session_id] = {
        'file_content': content,  # In production: store encrypted on disk
        'filename': safe_name,
        'file_hash': file_hash,
        'is_encrypted': is_encrypted,
        'created_at': datetime.utcnow(),
        'expires_at': datetime.utcnow() + timedelta(minutes=settings.SESSION_EXPIRE_MINUTES),
        'processed': False,
        'output_path': None,
        'client_ip': client_ip,
    }
    
    # Schedule cleanup
    background_tasks.add_task(cleanup_session, session_id, delay_minutes=settings.SESSION_EXPIRE_MINUTES)
    
    logger.info(f"File uploaded: session={session_id[:8]}..., encrypted={is_encrypted}")
    
    return UploadResponse(
        session_id=session_id,
        filename=safe_name,
        is_encrypted=is_encrypted,
        file_size_kb=round(len(content) / 1024, 2),
        message="File uploaded successfully. " + (
            "Please provide your PIN to process." if is_encrypted 
            else "File is ready to process."
        )
    )


@router.post("/process", response_model=ProcessResponse)
async def process_statement(
    request: Request,
    process_request: ProcessRequest,
):
    """
    Process the uploaded PDF statement with optional PIN.
    Validates PIN, extracts data, and generates Excel output.
    """
    client_ip = get_client_ip(request)
    session_id = process_request.session_id
    
    # Rate limiting
    if not rate_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests.")
    
    # Validate session
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail="Session not found or expired. Please upload your file again."
        )
    
    # Check session expiry
    if datetime.utcnow() > session['expires_at']:
        sessions.pop(session_id, None)
        raise HTTPException(
            status_code=410,
            detail="Session has expired. Please upload your file again."
        )
    
    # Check if already processed
    if session.get('processed') and session.get('output_path'):
        return ProcessResponse(
            success=True,
            download_token=session['download_token'],
            transaction_count=session.get('transaction_count', 0),
            warnings=session.get('warnings', []),
            message="Statement already processed. Download your file."
        )
    
    # PIN attempt tracking
    if session['is_encrypted']:
        if not process_request.pin:
            raise HTTPException(
                status_code=400,
                detail="PIN is required for encrypted PDF."
            )
        
        attempt_status = pin_tracker.check_and_record(session_id, False)
        if not attempt_status['allowed'] and attempt_status.get('locked'):
            raise HTTPException(
                status_code=423,
                detail=f"Too many failed attempts. Try again in {attempt_status['remaining_seconds']} seconds."
            )
    
    # Process PDF
    try:
        if session['is_encrypted']:
            result = pdf_processor.decrypt_and_extract(
                session['file_content'],
                process_request.pin
            )
        else:
            # Unencrypted - extract directly
            result = pdf_processor.decrypt_and_extract(
                session['file_content'],
                ""
            )
        
        if not result.success:
            if session['is_encrypted']:
                # Record failed PIN attempt
                attempt_status = pin_tracker.check_and_record(session_id, False)
                detail = result.error
                if attempt_status.get('attempts_left', 0) > 0:
                    detail += f" ({attempt_status['attempts_left']} attempts remaining)"
            else:
                detail = result.error
            
            raise HTTPException(status_code=401, detail=detail)
        
        # Successful decryption - update attempt tracking
        if session['is_encrypted']:
            pin_tracker.check_and_record(session_id, True)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Processing error: {e}")
        raise HTTPException(status_code=500, detail="Processing failed. Please try again.")
    
    # Parse statement
    try:
        parsed_statement = parser.parse(result.text_content)
        
        if not parsed_statement.transactions:
            raise HTTPException(
                status_code=422,
                detail="No transactions found in the statement. "
                       "Please ensure this is a valid MPesa statement."
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Parsing error: {e}")
        raise HTTPException(
            status_code=422,
            detail="Could not parse the statement. Please verify the file is a valid MPesa statement."
        )
    
    # Generate Excel
    try:
        excel_bytes = excel_generator.generate(parsed_statement)
        
        # Generate download token
        download_token = generate_session_id()
        
        # Save Excel file temporarily
        output_filename = f"mpesa_statement_{download_token[:8]}.xlsx"
        output_path = settings.OUTPUT_DIR / output_filename
        
        async with aiofiles.open(output_path, 'wb') as f:
            await f.write(excel_bytes)
        
        # Update session
        session['processed'] = True
        session['output_path'] = str(output_path)
        session['download_token'] = download_token
        session['transaction_count'] = len(parsed_statement.transactions)
        session['warnings'] = parsed_statement.parsing_warnings
        
        # Clear file content from memory after processing
        session['file_content'] = None
        
        logger.info(
            f"Statement processed: session={session_id[:8]}..., "
            f"transactions={len(parsed_statement.transactions)}"
        )
        
        return ProcessResponse(
            success=True,
            download_token=download_token,
            transaction_count=len(parsed_statement.transactions),
            parsing_warnings=parsed_statement.parsing_warnings[:10],  # Limit warnings
            statement_period=_format_period_string(parsed_statement.metadata),
            account_name=parsed_statement.metadata.account_name,
            message=f"Successfully extracted {len(parsed_statement.transactions)} transactions."
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Excel generation error: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate Excel file.")


@router.get("/download/{download_token}")
async def download_excel(
    request: Request,
    download_token: str,
    background_tasks: BackgroundTasks,
):
    """Download the generated Excel file."""
    client_ip = get_client_ip(request)
    
    if not rate_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests.")
    
    # Find session with this download token
    matching_session = None
    for session_id, session in sessions.items():
        if session.get('download_token') == download_token:
            matching_session = session
            break
    
    if not matching_session:
        raise HTTPException(
            status_code=404,
            detail="Download link not found or expired."
        )
    
    output_path = Path(matching_session['output_path'])
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="File no longer available.")
    
    # Generate safe filename for download
    safe_download_name = f"MPesa_Statement_{datetime.now().strftime('%Y%m%d')}.xlsx"
    
    # Schedule file deletion after download
    background_tasks.add_task(delete_file, str(output_path), delay_seconds=60)
    
    return FileResponse(
        path=str(output_path),
        filename=safe_download_name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_download_name}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store, no-cache, must-revalidate",
        }
    )


# ─── Background Tasks ─────────────────────────────────────────

async def cleanup_session(session_id: str, delay_minutes: int) -> None:
    """Clean up session data after delay."""
    await asyncio.sleep(delay_minutes * 60)
    if session_id in sessions:
        session = sessions[session_id]
        # Delete output file if exists
        if session.get('output_path'):
            output_path = Path(session['output_path'])
            if output_path.exists():
                output_path.unlink()
        sessions.pop(session_id, None)
        logger.info(f"Session {session_id[:8]}... cleaned up")


async def delete_file(file_path: str, delay_seconds: int = 0) -> None:
    """Delete file after optional delay."""
    if delay_seconds:
        await asyncio.sleep(delay_seconds)
    path = Path(file_path)
    if path.exists():
        path.unlink()


def _format_period_string(metadata) -> str:
    if metadata.statement_period_start and metadata.statement_period_end:
        return (
            f"{metadata.statement_period_start.strftime('%d %b %Y')} to "
            f"{metadata.statement_period_end.strftime('%d %b %Y')}"
        )
    return ""