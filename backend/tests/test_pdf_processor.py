# backend/tests/test_pdf_processor.py
import pytest
from app.services.pdf_processor import SecurePDFProcessor

processor = SecurePDFProcessor()

def test_invalid_file_rejected():
    result = processor.validate_pdf(b"not a pdf")
    assert result[0] is False

def test_valid_pdf_detected():
    # Load test PDF
    with open("tests/fixtures/sample_unencrypted.pdf", "rb") as f:
        content = f.read()
    is_valid, _, _ = processor.validate_pdf(content)
    assert is_valid is True

def test_wrong_pin_returns_clear_error():
    with open("tests/fixtures/sample_encrypted.pdf", "rb") as f:
        content = f.read()
    result = processor.decrypt_and_extract(content, "wrongpin")
    assert result.success is False
    assert "Incorrect PIN" in result.error
    # PIN must never appear in error message
    assert "wrongpin" not in result.error

def test_empty_pin_rejected():
    result = processor.decrypt_and_extract(b"%PDF-test", "")
    assert result.success is False