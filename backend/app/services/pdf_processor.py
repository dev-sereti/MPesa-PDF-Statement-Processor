# backend/app/services/pdf_processor.py
import pikepdf
import pdfplumber
import io
import logging
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PDFProcessingResult:
    success: bool
    text_content: Optional[str] = None
    page_count: int = 0
    error: Optional[str] = None
    is_encrypted: bool = False


class SecurePDFProcessor:
    """
    Handles encrypted PDF decryption and text extraction.
    Uses pikepdf for encryption handling and pdfplumber for extraction.
    """
    
    SUPPORTED_ENCRYPTION_ALGORITHMS = ['AES-128', 'AES-256', 'RC4-128']
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def validate_pdf(self, file_content: bytes) -> Tuple[bool, str, bool]:
        """
        Validate that the file is a valid PDF and check encryption status.
        
        Returns: (is_valid, message, is_encrypted)
        """
        # Check PDF magic bytes
        if not file_content.startswith(b'%PDF'):
            return False, "File is not a valid PDF", False
        
        try:
            pdf_stream = io.BytesIO(file_content)
            
            try:
                with pikepdf.open(pdf_stream) as pdf:
                    page_count = len(pdf.pages)
                    return True, f"Valid PDF with {page_count} pages", False
            except pikepdf.PasswordError:
                # PDF is encrypted - this is expected
                return True, "PDF is password-protected", True
            except pikepdf.PdfError as e:
                return False, f"Invalid PDF structure: {str(e)}", False
                
        except Exception as e:
            self.logger.error(f"PDF validation error: {e}")
            return False, "Could not process PDF file", False
    
    def decrypt_and_extract(
        self, 
        file_content: bytes, 
        pin: str
    ) -> PDFProcessingResult:
        """
        Decrypt PDF with provided PIN and extract text content.
        
        Security: PIN is never logged, stored, or included in errors.
        """
        if not pin or not pin.strip():
            return PDFProcessingResult(
                success=False,
                error="PIN cannot be empty",
                is_encrypted=True
            )
        
        # Validate PIN format (MPesa PINs are typically numeric)
        if not self._validate_pin_format(pin):
            return PDFProcessingResult(
                success=False,
                error="Invalid PIN format",
                is_encrypted=True
            )
        
        try:
            pdf_stream = io.BytesIO(file_content)
            
            # Attempt decryption with pikepdf
            try:
                with pikepdf.open(pdf_stream, password=pin) as pdf:
                    # Successfully decrypted
                    self.logger.info(f"PDF decrypted successfully, {len(pdf.pages)} pages")
                    
                    # Save decrypted PDF to memory buffer
                    decrypted_buffer = io.BytesIO()
                    pdf.save(decrypted_buffer)
                    decrypted_buffer.seek(0)
                    
                    # Extract text using pdfplumber
                    text_content = self._extract_text(decrypted_buffer)
                    
                    if not text_content:
                        return PDFProcessingResult(
                            success=False,
                            error="No text content found in PDF. The PDF may contain scanned images.",
                            is_encrypted=False
                        )
                    
                    return PDFProcessingResult(
                        success=True,
                        text_content=text_content,
                        page_count=len(pdf.pages),
                        is_encrypted=True
                    )
                    
            except pikepdf.PasswordError:
                self.logger.warning("Incorrect PIN provided for PDF decryption")
                return PDFProcessingResult(
                    success=False,
                    error="Incorrect PIN. Please check your statement PIN and try again.",
                    is_encrypted=True
                )
                
        except Exception as e:
            self.logger.error(f"PDF processing error: {type(e).__name__}: {e}")
            return PDFProcessingResult(
                success=False,
                error="An error occurred while processing the PDF. Please try again.",
                is_encrypted=True
            )
        finally:
            # Explicitly clear PIN from memory (best effort)
            pin = None
    
    def _extract_text(self, pdf_buffer: io.BytesIO) -> Optional[str]:
        """Extract text from decrypted PDF using pdfplumber."""
        try:
            all_text = []
            
            with pdfplumber.open(pdf_buffer) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    # Extract tables first (better for transaction data)
                    tables = page.extract_tables()
                    
                    if tables:
                        for table in tables:
                            for row in table:
                                if row:
                                    cleaned_row = [
                                        str(cell).strip() if cell else ''
                                        for cell in row
                                    ]
                                    all_text.append('\t'.join(cleaned_row))
                    else:
                        # Fall back to text extraction
                        text = page.extract_text(
                            x_tolerance=3,
                            y_tolerance=3,
                            layout=True,
                            x_density=7.25,
                            y_density=13
                        )
                        if text:
                            all_text.append(text)
            
            return '\n'.join(all_text) if all_text else None
            
        except Exception as e:
            self.logger.error(f"Text extraction error: {e}")
            return None
    
    def _validate_pin_format(self, pin: str) -> bool:
        """
        Validate PIN format without logging the actual PIN.
        MPesa PINs are typically 4-8 digit numeric codes,
        but some statements use phone numbers as PINs.
        """
        if not pin:
            return False
        
        pin = pin.strip()
        
        # Length check
        if not (4 <= len(pin) <= 20):
            return False
        
        # Allow digits only or digits with common separators
        import re
        if re.match(r'^[\d]+$', pin):
            return True
        
        # Some MPesa statements use phone number format
        if re.match(r'^\+?[\d\s\-]{8,15}$', pin):
            return True
        
        return False