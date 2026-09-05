"""Text extraction from regulation PDFs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pypdf import PdfReader

from mini_aec_agent.exceptions import DataSourceError

MAX_PDF_FILE_BYTES = 100 * 1024 * 1024
MAX_PDF_PAGES = 2000


def extract_pdf_pages(pdf_file: str | Path) -> list[dict[str, Any]]:
    """Extract every PDF page as a numbered text record."""

    path = Path(pdf_file).expanduser().resolve()
    if not path.is_file():
        raise DataSourceError(f"Regulation PDF was not found: {path}")
    if path.suffix.casefold() != ".pdf":
        raise DataSourceError("Regulation source must use the .pdf extension.")

    try:
        if path.stat().st_size > MAX_PDF_FILE_BYTES:
            raise DataSourceError(
                f"Regulation PDF exceeds the {MAX_PDF_FILE_BYTES}-byte safety limit."
            )
        reader = PdfReader(path)
        if len(reader.pages) > MAX_PDF_PAGES:
            raise DataSourceError(
                f"Regulation PDF exceeds the {MAX_PDF_PAGES}-page safety limit."
            )
        return [
            {"page": page_number, "text": (page.extract_text() or "").strip()}
            for page_number, page in enumerate(reader.pages, start=1)
        ]
    except DataSourceError:
        raise
    except Exception as error:
        raise DataSourceError(f"Could not extract regulation PDF: {path}") from error
