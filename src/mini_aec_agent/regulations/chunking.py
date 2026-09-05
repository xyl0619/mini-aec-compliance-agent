"""Page-aware regulation text normalization and chunking."""

from __future__ import annotations

import re
from typing import Any

DEFAULT_CHUNK_SIZE = 220
DEFAULT_CHUNK_OVERLAP = 40


def normalize_text(text: str) -> str:
    """Normalize extracted PDF text while retaining readable sentences."""

    text = text.replace("\u00a0", " ")
    text = re.sub(r"-\s*\n\s*(?=[a-z])", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def infer_section_hint(text: str) -> str | None:
    """Best-effort heading hint from the first short non-empty PDF line."""

    for raw_line in text.splitlines()[:12]:
        line = normalize_text(raw_line)
        if not line or len(line) > 120:
            continue
        if re.match(r"^(?:chapter|section|part|appendix|\d+(?:\.\d+)*)\b", line, re.I):
            return line
        if len(line.split()) <= 12 and line.isupper():
            return line
    return None


def split_into_word_chunks(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """Split normalized text into overlapping word windows."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0.")
    if overlap < 0:
        raise ValueError("overlap cannot be negative.")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size.")

    words = normalize_text(text).split()
    if not words:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start = end - overlap
    return chunks


def chunk_pages(
    pages: list[dict[str, Any]],
    *,
    source_name: str,
    source_url: str,
    document_id: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[dict[str, Any]]:
    """Create stable, source-bearing chunks from extracted PDF pages."""

    chunks: list[dict[str, Any]] = []
    for page in pages:
        page_number = int(page["page"])
        page_text = str(page.get("text", ""))
        section_hint = infer_section_hint(page_text)

        for chunk_number, chunk_text in enumerate(
            split_into_word_chunks(page_text, chunk_size, overlap), start=1
        ):
            chunks.append(
                {
                    "chunk_id": (
                        f"{document_id}-p{page_number:03d}-c{chunk_number:03d}"
                    ),
                    "document_id": document_id,
                    "source": source_name,
                    "source_url": source_url,
                    "pdf_page": page_number,
                    "chunk_on_page": chunk_number,
                    "section_hint": section_hint,
                    "word_count": len(chunk_text.split()),
                    "text": chunk_text,
                }
            )
    return chunks
