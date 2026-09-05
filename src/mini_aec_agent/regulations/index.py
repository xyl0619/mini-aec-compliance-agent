"""Build a reproducible local regulation retrieval artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from mini_aec_agent.config import get_settings
from mini_aec_agent.io_utils import atomic_write_text
from mini_aec_agent.regulations.chunking import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    chunk_pages,
)
from mini_aec_agent.regulations.extract import extract_pdf_pages
from mini_aec_agent.regulations.models import RegulationIndex

DEFAULT_SOURCE_NAME = "Design Manual: Barrier Free Access 2008 (2025 Edition)"
DEFAULT_SOURCE_URL = (
    "https://www.bd.gov.hk/doc/en/resources/codes-and-references/"
    "code-and-design-manuals/BFA2008_e.pdf"
)
DEFAULT_DOCUMENT_ID = "BFA2025"


def _sha256_file(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_index(
    pdf_file: str | Path,
    output_file: str | Path,
    *,
    source_name: str = DEFAULT_SOURCE_NAME,
    source_url: str = DEFAULT_SOURCE_URL,
    document_id: str = DEFAULT_DOCUMENT_ID,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> dict[str, Any]:
    """Extract, chunk, and save one regulation PDF index."""

    pdf_path = Path(pdf_file).expanduser().resolve()
    output_path = Path(output_file).expanduser().resolve()
    pages = extract_pdf_pages(pdf_path)
    chunks = chunk_pages(
        pages,
        source_name=source_name,
        source_url=source_url,
        document_id=document_id,
        chunk_size=chunk_size,
        overlap=overlap,
    )
    usable_pages = sum(bool(str(page["text"]).strip()) for page in pages)
    total_words = sum(int(chunk["word_count"]) for chunk in chunks)

    artifact: dict[str, Any] = {
        "metadata": {
            "schema_version": 1,
            "document_id": document_id,
            "source_name": source_name,
            "source_url": source_url,
            "source_sha256": _sha256_file(pdf_path),
            "total_pdf_pages": len(pages),
            "pages_with_text": usable_pages,
            "blank_pages": len(pages) - usable_pages,
            "chunk_size_words": chunk_size,
            "chunk_overlap_words": overlap,
            "total_chunks": len(chunks),
            "average_words_per_chunk": (
                round(total_words / len(chunks), 2) if chunks else 0
            ),
        },
        "chunks": chunks,
    }
    RegulationIndex.model_validate(artifact)

    atomic_write_text(
        output_path,
        json.dumps(artifact, indent=2, ensure_ascii=False),
    )
    return artifact


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Build a regulation retrieval index.")
    parser.add_argument("--pdf", type=Path, default=settings.regulation_pdf_file)
    parser.add_argument("--output", type=Path, default=settings.regulation_index_file)
    args = parser.parse_args()

    artifact = build_index(args.pdf, args.output)
    print(
        f"Indexed {artifact['metadata']['total_chunks']} chunks from "
        f"{artifact['metadata']['total_pdf_pages']} pages into {args.output}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
