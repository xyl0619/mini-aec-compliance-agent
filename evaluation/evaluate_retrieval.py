"""Offline page/chunk retrieval benchmark for the configured regulation index."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mini_aec_agent.config import get_settings
from mini_aec_agent.exceptions import DataSourceError
from mini_aec_agent.io_utils import atomic_write_text
from mini_aec_agent.json_utils import reject_duplicate_keys, reject_non_finite_number
from mini_aec_agent.regulations.retriever import RegulationRetriever

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CASES_FILE = BASE_DIR / "regulation_retrieval_cases.json"
DEFAULT_RESULTS_FILE = BASE_DIR / "retrieval_results.json"
MAX_EVALUATION_FILE_BYTES = 4 * 1024 * 1024
MAX_EVALUATION_CASES = 10_000


def _load_cases(cases_file: str | Path) -> list[dict[str, Any]]:
    path = Path(cases_file).expanduser().resolve()
    try:
        if path.stat().st_size > MAX_EVALUATION_FILE_BYTES:
            raise DataSourceError("Retrieval case file exceeds the safety limit.")
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=reject_non_finite_number,
            object_pairs_hook=reject_duplicate_keys,
        )
    except DataSourceError:
        raise
    except (OSError, json.JSONDecodeError, RecursionError, ValueError) as error:
        raise DataSourceError(f"Could not load retrieval cases: {path}") from error
    if not isinstance(payload, list) or len(payload) > MAX_EVALUATION_CASES:
        raise DataSourceError("Retrieval cases must be a JSON list.")

    cases: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for case in payload:
        if not isinstance(case, dict):
            raise DataSourceError("Every retrieval case must be an object.")
        case_id = case.get("id")
        query = case.get("query")
        expected_ids = case.get("expected_chunk_ids")
        if (
            not isinstance(case_id, str)
            or not case_id.strip()
            or not isinstance(query, str)
            or not query.strip()
            or not isinstance(expected_ids, list)
            or not expected_ids
            or len(case_id) > 128
            or len(query) > 1000
            or len(expected_ids) > 100
            or any(
                not isinstance(value, str) or not value.strip() or len(value) > 256
                for value in expected_ids
            )
            or len(expected_ids) != len(set(expected_ids))
        ):
            raise DataSourceError("Retrieval cases contain invalid required fields.")
        normalized_case_id = case_id.casefold()
        if normalized_case_id in seen_ids:
            raise DataSourceError(f"Duplicate retrieval case id: {case_id}")
        seen_ids.add(normalized_case_id)
        cases.append(case)
    return cases


def evaluate_retrieval(
    index_file: str | Path,
    cases_file: str | Path = DEFAULT_CASES_FILE,
    *,
    top_k: int = 5,
) -> dict[str, Any]:
    """Calculate hit-rate and MRR against human-selected relevant chunks."""

    cases = _load_cases(cases_file)
    retriever = RegulationRetriever(index_file)
    results = []

    for case in cases:
        retrieval = retriever.retrieve(case["query"], top_k)
        returned_ids = [result["chunk_id"] for result in retrieval["results"]]
        relevant_ids = set(case["expected_chunk_ids"])
        relevant_ranks = [
            rank
            for rank, chunk_id in enumerate(returned_ids, start=1)
            if chunk_id in relevant_ids
        ]
        first_relevant_rank = min(relevant_ranks, default=None)
        results.append(
            {
                "id": case["id"],
                "query": case["query"],
                "expected_chunk_ids": case["expected_chunk_ids"],
                "returned_chunk_ids": returned_ids,
                "hit": first_relevant_rank is not None,
                "first_relevant_rank": first_relevant_rank,
                "reciprocal_rank": (
                    round(1 / first_relevant_rank, 4) if first_relevant_rank else 0.0
                ),
            }
        )

    case_count = len(results)
    hit_count = sum(result["hit"] for result in results)
    reciprocal_rank_sum = sum(result["reciprocal_rank"] for result in results)
    return {
        "evaluation_name": "Mini AEC Regulation Retrieval Evaluation",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scope_note": (
            "A small bootstrap benchmark over one regulation document. Relevant "
            "chunks were manually selected and should be expanded before making "
            "general retrieval-quality claims."
        ),
        "configuration": {
            "index_file": Path(index_file).name,
            "top_k": top_k,
            "retriever": "BM25 with query-bigram bonus",
        },
        "summary": {
            "total_cases": case_count,
            "hits": hit_count,
            "hit_rate_at_k": round(hit_count / case_count, 4) if case_count else 0.0,
            "mean_reciprocal_rank": (
                round(reciprocal_rank_sum / case_count, 4) if case_count else 0.0
            ),
        },
        "results": results,
    }


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Evaluate regulation retrieval.")
    parser.add_argument("--index", type=Path, default=settings.regulation_index_file)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_FILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_RESULTS_FILE)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    result = evaluate_retrieval(args.index, args.cases, top_k=args.top_k)
    atomic_write_text(
        args.output,
        json.dumps(result, indent=2, ensure_ascii=False),
    )
    print(json.dumps(result["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
