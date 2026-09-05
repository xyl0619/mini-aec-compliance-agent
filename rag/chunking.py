"""Backward-compatible regulation chunking imports."""

from mini_aec_agent.regulations.chunking import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    chunk_pages,
    infer_section_hint,
    normalize_text,
    split_into_word_chunks,
)

__all__ = [
    "DEFAULT_CHUNK_OVERLAP",
    "DEFAULT_CHUNK_SIZE",
    "chunk_pages",
    "infer_section_hint",
    "normalize_text",
    "split_into_word_chunks",
]
