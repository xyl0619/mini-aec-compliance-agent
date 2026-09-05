"""Validated schemas for generated regulation retrieval indexes."""

from __future__ import annotations

from typing import Any, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RegulationChunk(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True, str_strip_whitespace=True)

    chunk_id: str = Field(min_length=1, max_length=256)
    document_id: str = Field(min_length=1, max_length=128)
    source: str = Field(min_length=1, max_length=500)
    source_url: str | None = Field(default=None, max_length=2000)
    pdf_page: int = Field(ge=1)
    section_hint: str | None = Field(default=None, max_length=500)
    text: str = Field(min_length=1, max_length=100_000)

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("source_url must be an absolute HTTP(S) URL")
        return value


class RegulationIndex(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True, str_strip_whitespace=True)

    metadata: dict[str, Any] = Field(default_factory=dict)
    chunks: list[RegulationChunk] = Field(max_length=100_000)

    @model_validator(mode="after")
    def ensure_unique_chunk_ids(self) -> Self:
        chunk_ids = [chunk.chunk_id for chunk in self.chunks]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("chunk_id values must be unique")
        return self
