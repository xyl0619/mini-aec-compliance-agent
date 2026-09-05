from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.evaluate_retrieval import _load_cases, evaluate_retrieval
from mini_aec_agent.exceptions import DataSourceError


def test_retrieval_evaluation_calculates_hit_rate_and_mrr(tmp_path: Path) -> None:
    index_file = tmp_path / "index.json"
    cases_file = tmp_path / "cases.json"
    index_file.write_text(
        json.dumps(
            {
                "chunks": [
                    {
                        "chunk_id": "door-rule",
                        "document_id": "DEMO",
                        "source": "Demo",
                        "pdf_page": 1,
                        "text": "Doors require a clear accessible width.",
                    },
                    {
                        "chunk_id": "ramp-rule",
                        "document_id": "DEMO",
                        "source": "Demo",
                        "pdf_page": 2,
                        "text": "Ramps require a safe gradient.",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    cases_file.write_text(
        json.dumps(
            [
                {
                    "id": "doors",
                    "query": "accessible door width",
                    "expected_chunk_ids": ["door-rule"],
                },
                {
                    "id": "missing",
                    "query": "lift dimensions",
                    "expected_chunk_ids": ["lift-rule"],
                },
            ]
        ),
        encoding="utf-8",
    )

    result = evaluate_retrieval(index_file, cases_file, top_k=1)

    assert result["summary"]["total_cases"] == 2
    assert result["summary"]["hits"] == 1
    assert result["summary"]["hit_rate_at_k"] == 0.5
    assert result["summary"]["mean_reciprocal_rank"] == 0.5
    assert result["configuration"]["index_file"] == "index.json"


def test_retrieval_evaluation_rejects_invalid_cases(tmp_path: Path) -> None:
    cases_file = tmp_path / "cases.json"
    cases_file.write_text(
        '[{"id":"duplicate","query":"doors","expected_chunk_ids":["a"]},'
        '{"id":"duplicate","query":"ramps","expected_chunk_ids":["b"]}]',
        encoding="utf-8",
    )

    with pytest.raises(DataSourceError, match="Duplicate"):
        _load_cases(cases_file)

    cases_file.write_text(
        '[{"id":"case","query":"doors","expected_chunk_ids":["a","a"]}]',
        encoding="utf-8",
    )
    with pytest.raises(DataSourceError, match="invalid"):
        _load_cases(cases_file)
