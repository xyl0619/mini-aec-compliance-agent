"""Deterministic BM25 retrieval over regulation chunks."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from mini_aec_agent.exceptions import DataSourceError
from mini_aec_agent.json_utils import reject_duplicate_keys, reject_non_finite_number
from mini_aec_agent.regulations.models import RegulationIndex

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "what",
    "when",
    "where",
    "which",
    "who",
    "with",
}
MAX_INDEX_FILE_BYTES = 64 * 1024 * 1024
MAX_QUERY_LENGTH = 1000


def tokenize(text: str) -> list[str]:
    """Return lowercase lexical tokens suitable for technical retrieval."""

    tokens = re.findall(r"[a-zA-Z0-9]+", text.casefold())
    return [token for token in tokens if token not in STOPWORDS and len(token) > 1]


class RegulationRetriever:
    """Load one generated index and rank chunks using BM25 plus phrase overlap."""

    MAX_TOP_K = 20

    def __init__(self, index_file: str | Path, *, k1: float = 1.5, b: float = 0.75):
        self.index_file = Path(index_file).expanduser().resolve()
        if not math.isfinite(k1) or k1 <= 0:
            raise ValueError("k1 must be a finite number greater than 0.")
        if not math.isfinite(b) or not 0 <= b <= 1:
            raise ValueError("b must be a finite number between 0 and 1.")
        self.k1 = k1
        self.b = b
        self.index = self._load_index()
        self.chunks: list[dict[str, Any]] = self.index["chunks"]
        self.tokenized_chunks = [tokenize(str(chunk["text"])) for chunk in self.chunks]
        self.document_frequencies = self._document_frequencies()
        self.average_document_length = (
            sum(len(tokens) for tokens in self.tokenized_chunks) / len(self.chunks)
            if self.chunks
            else 0.0
        )

    def _load_index(self) -> dict[str, Any]:
        if not self.index_file.is_file():
            raise DataSourceError(
                "Regulation index was not found. Run `python -m rag.build_index` "
                f"or configure MINI_AEC_REGULATION_INDEX: {self.index_file}"
            )

        try:
            if self.index_file.stat().st_size > MAX_INDEX_FILE_BYTES:
                raise DataSourceError(
                    f"Regulation index exceeds {MAX_INDEX_FILE_BYTES} bytes."
                )
            payload = json.loads(
                self.index_file.read_text(encoding="utf-8"),
                parse_constant=reject_non_finite_number,
                object_pairs_hook=reject_duplicate_keys,
            )
            validated = RegulationIndex.model_validate(payload)
        except DataSourceError:
            raise
        except (
            OSError,
            json.JSONDecodeError,
            RecursionError,
            ValueError,
            ValidationError,
        ) as error:
            raise DataSourceError(
                f"Could not load regulation index: {self.index_file}"
            ) from error
        return validated.model_dump(mode="json")

    def _document_frequencies(self) -> Counter[str]:
        frequencies: Counter[str] = Counter()
        for tokens in self.tokenized_chunks:
            frequencies.update(set(tokens))
        return frequencies

    def _score(self, query_tokens: list[str], index: int) -> float:
        tokens = self.tokenized_chunks[index]
        if not tokens or not self.average_document_length:
            return 0.0

        counts = Counter(tokens)
        document_count = len(self.chunks)
        score = 0.0
        for token in set(query_tokens):
            term_frequency = counts.get(token, 0)
            if not term_frequency:
                continue
            document_frequency = self.document_frequencies[token]
            inverse_document_frequency = math.log(
                1
                + (document_count - document_frequency + 0.5)
                / (document_frequency + 0.5)
            )
            length_normalization = (
                1 - self.b + self.b * (len(tokens) / self.average_document_length)
            )
            score += (
                inverse_document_frequency
                * (term_frequency * (self.k1 + 1))
                / (term_frequency + self.k1 * length_normalization)
            )

        query_bigrams = set(zip(query_tokens, query_tokens[1:]))
        chunk_bigrams = set(zip(tokens, tokens[1:]))
        score += 0.35 * len(query_bigrams & chunk_bigrams)
        return score

    def retrieve(self, query: str, top_k: int = 5) -> dict[str, Any]:
        """Return ranked chunks with source and page citations."""

        if not query.strip():
            raise ValueError("Regulation query cannot be empty.")
        if len(query) > MAX_QUERY_LENGTH:
            raise ValueError(
                f"Regulation query cannot exceed {MAX_QUERY_LENGTH} characters."
            )
        if isinstance(top_k, bool) or not isinstance(top_k, int):
            raise ValueError("top_k must be an integer.")
        if not 1 <= top_k <= self.MAX_TOP_K:
            raise ValueError(f"top_k must be between 1 and {self.MAX_TOP_K}.")

        query_tokens = tokenize(query)
        if not query_tokens:
            return {"query": query, "count": 0, "results": []}

        scored = [
            (self._score(query_tokens, index), index)
            for index in range(len(self.chunks))
        ]
        scored = [item for item in scored if item[0] > 0]
        scored.sort(
            key=lambda item: (
                -item[0],
                int(self.chunks[item[1]].get("pdf_page", 0)),
                str(self.chunks[item[1]].get("chunk_id", "")),
            )
        )

        results: list[dict[str, Any]] = []
        for rank, (score, index) in enumerate(scored[:top_k], start=1):
            chunk = self.chunks[index]
            source = str(chunk.get("source", "Unknown source"))
            page = chunk.get("pdf_page")
            matched_terms = sorted(
                set(query_tokens) & set(self.tokenized_chunks[index])
            )
            results.append(
                {
                    "rank": rank,
                    "score": round(score, 4),
                    "chunk_id": chunk.get("chunk_id"),
                    "document_id": chunk.get("document_id"),
                    "source": source,
                    "source_url": chunk.get("source_url"),
                    "pdf_page": page,
                    "section_hint": chunk.get("section_hint"),
                    "matched_terms": matched_terms,
                    "citation": f"{source}, PDF p.{page}",
                    "text": chunk["text"],
                }
            )

        return {"query": query, "count": len(results), "results": results}


def main() -> int:
    import argparse

    from mini_aec_agent.config import get_settings

    settings = get_settings()
    parser = argparse.ArgumentParser(description="Search the regulation index.")
    parser.add_argument("query")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--index", type=Path, default=settings.regulation_index_file)
    args = parser.parse_args()

    result = RegulationRetriever(args.index).retrieve(args.query, args.top_k)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
