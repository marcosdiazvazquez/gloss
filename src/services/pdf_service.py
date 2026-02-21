"""PDF loading and base64 encoding for LLM submission."""

from __future__ import annotations

import base64
from pathlib import Path

MAX_PDF_SIZE = 32 * 1024 * 1024  # 32 MB Anthropic limit


def validate_pdf(pdf_path: Path) -> None:
    """Raise ValueError if the PDF exceeds the Anthropic size limit."""
    size = pdf_path.stat().st_size
    if size > MAX_PDF_SIZE:
        mb = size / (1024 * 1024)
        raise ValueError(
            f"PDF is {mb:.1f} MB, which exceeds the 32 MB limit. "
            "Try a smaller file or compress the PDF."
        )


def load_pdf_base64(pdf_path: Path) -> str:
    """Read a PDF file and return its base64-encoded content."""
    validate_pdf(pdf_path)
    return base64.standard_b64encode(pdf_path.read_bytes()).decode("ascii")
