from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from mini_aec_agent.agent import execute_tool
from mini_aec_agent.config import get_settings
from mini_aec_agent.exceptions import DataSourceError
from mini_aec_agent.regulation_tools import retrieve_regulations
from mini_aec_agent.regulations import index as index_module
from mini_aec_agent.regulations.chunking import (
    chunk_pages,
    infer_section_hint,
    normalize_text,
    split_into_word_chunks,
)
from mini_aec_agent.regulations.extract import extract_pdf_pages
from mini_aec_agent.regulations.retriever import RegulationRetriever, tokenize


def _write_index(path: Path) -> None:
    payload = {
        "metadata": {"schema_version": 1},
        "chunks": [
            {
                "chunk_id": "DEMO-p001-c001",
                "document_id": "DEMO",
                "source": "Demo Standard",
                "source_url": "https://example.com/standard.pdf",
                "pdf_page": 1,
                "section_hint": "Doors",
                "text": "Accessible doors require a clear width of 850 millimetres.",
            },
            {
                "chunk_id": "DEMO-p002-c001",
                "document_id": "DEMO",
                "source": "Demo Standard",
                "source_url": "https://example.com/standard.pdf",
                "pdf_page": 2,
                "section_hint": "Ramps",
                "text": "Ramps require handrails and a safe gradient.",
            },
            {
                "chunk_id": "DEMO-p003-c001",
                "document_id": "DEMO",
                "source": "Demo Standard",
                "source_url": "https://example.com/standard.pdf",
                "pdf_page": 3,
                "section_hint": "Lifts",
                "text": "Accessible lift cars provide wheelchair turning space.",
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_normalize_and_tokenize_technical_text() -> None:
    assert normalize_text("clear-\nwidth\u00a0 850 mm") == "clearwidth 850 mm"
    assert tokenize("The clear width is 850 mm") == ["clear", "width", "850", "mm"]


def test_chunking_retains_overlap_and_source_metadata() -> None:
    pages = [{"page": 7, "text": "SECTION 7\none two three four five six"}]

    chunks = chunk_pages(
        pages,
        source_name="Demo",
        source_url="https://example.com",
        document_id="DOC",
        chunk_size=4,
        overlap=1,
    )

    assert chunks[0]["chunk_id"] == "DOC-p007-c001"
    assert chunks[0]["source_url"] == "https://example.com"
    assert chunks[0]["section_hint"] == "SECTION 7"
    assert chunks[0]["text"].split()[-1] == chunks[1]["text"].split()[0]


@pytest.mark.parametrize(("chunk_size", "overlap"), [(0, 0), (10, -1), (10, 10)])
def test_chunking_rejects_invalid_windows(chunk_size: int, overlap: int) -> None:
    with pytest.raises(ValueError):
        split_into_word_chunks("some text", chunk_size, overlap)


def test_empty_text_and_missing_section_hint() -> None:
    assert split_into_word_chunks("   ") == []
    assert infer_section_hint("a normal sentence that is not a heading") is None


def test_retriever_ranks_relevant_chunk_and_builds_citation(tmp_path: Path) -> None:
    index_file = tmp_path / "index.json"
    _write_index(index_file)

    result = RegulationRetriever(index_file).retrieve(
        "minimum accessible door width", 2
    )

    first = result["results"][0]
    assert first["chunk_id"] == "DEMO-p001-c001"
    assert first["pdf_page"] == 1
    assert first["citation"] == "Demo Standard, PDF p.1"
    assert "width" in first["matched_terms"]


def test_retriever_handles_stopword_only_query(tmp_path: Path) -> None:
    index_file = tmp_path / "index.json"
    _write_index(index_file)

    assert RegulationRetriever(index_file).retrieve("the and", 5)["results"] == []


@pytest.mark.parametrize(
    ("query", "top_k"), [("", 5), ("door", 0), ("door", 21), ("door", True)]
)
def test_retriever_validates_query_and_limit(
    tmp_path: Path, query: str, top_k: int
) -> None:
    index_file = tmp_path / "index.json"
    _write_index(index_file)

    with pytest.raises(ValueError):
        RegulationRetriever(index_file).retrieve(query, top_k)


def test_retriever_validates_index_shape(tmp_path: Path) -> None:
    missing_file = tmp_path / "missing.json"
    with pytest.raises(DataSourceError, match="not found"):
        RegulationRetriever(missing_file)

    invalid_json = tmp_path / "invalid.json"
    invalid_json.write_text("not-json", encoding="utf-8")
    with pytest.raises(DataSourceError, match="Could not load"):
        RegulationRetriever(invalid_json)

    missing_chunks = tmp_path / "missing-chunks.json"
    missing_chunks.write_text("{}", encoding="utf-8")
    with pytest.raises(DataSourceError, match="Could not load"):
        RegulationRetriever(missing_chunks)

    missing_text = tmp_path / "missing-text.json"
    missing_text.write_text('{"chunks": [{}]}', encoding="utf-8")
    with pytest.raises(DataSourceError, match="Could not load"):
        RegulationRetriever(missing_text)


@pytest.mark.parametrize(("k1", "b"), [(0, 0.75), (1.5, -0.1), (1.5, 1.1)])
def test_retriever_rejects_invalid_scoring_parameters(
    tmp_path: Path, k1: float, b: float
) -> None:
    index_file = tmp_path / "index.json"
    _write_index(index_file)

    with pytest.raises(ValueError):
        RegulationRetriever(index_file, k1=k1, b=b)


def test_retriever_rejects_duplicate_chunks_and_long_queries(tmp_path: Path) -> None:
    index_file = tmp_path / "index.json"
    _write_index(index_file)
    payload = json.loads(index_file.read_text(encoding="utf-8"))
    payload["chunks"].append(dict(payload["chunks"][0]))
    index_file.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(DataSourceError, match="Could not load"):
        RegulationRetriever(index_file)

    _write_index(index_file)
    with pytest.raises(ValueError, match="cannot exceed"):
        RegulationRetriever(index_file).retrieve("x" * 1001)


def test_retriever_rejects_invalid_source_url_and_duplicate_keys(
    tmp_path: Path,
) -> None:
    index_file = tmp_path / "index.json"
    _write_index(index_file)
    payload = json.loads(index_file.read_text(encoding="utf-8"))
    payload["chunks"][0]["source_url"] = "file:///private/source.pdf"
    index_file.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(DataSourceError, match="Could not load"):
        RegulationRetriever(index_file)

    index_file.write_text('{"chunks":[],"chunks":[]}', encoding="utf-8")
    with pytest.raises(DataSourceError, match="Could not load"):
        RegulationRetriever(index_file)


def test_regulation_tool_and_agent_dispatch_use_configured_index(
    tmp_path: Path,
) -> None:
    index_file = tmp_path / "index.json"
    _write_index(index_file)
    settings = replace(get_settings(), regulation_index_file=index_file)

    direct = retrieve_regulations("ramp gradient", 1, settings)
    dispatched = execute_tool(
        "retrieve_regulations", {"query": "ramp gradient", "top_k": 1}, settings
    )

    assert direct["results"][0]["pdf_page"] == 2
    assert dispatched["results"][0]["chunk_id"] == "DEMO-p002-c001"


def test_agent_validates_regulation_tool_inputs() -> None:
    assert "error" in execute_tool("retrieve_regulations", {})
    assert "error" in execute_tool(
        "retrieve_regulations", {"query": "doors", "top_k": "five"}
    )
    assert "error" in execute_tool(
        "retrieve_regulations", {"query": "doors", "top_k": 21}
    )


def test_build_index_writes_reproducible_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf_file = tmp_path / "source.pdf"
    output_file = tmp_path / "index.json"
    pdf_file.write_bytes(b"test-pdf-content")
    monkeypatch.setattr(
        index_module,
        "extract_pdf_pages",
        lambda path: [{"page": 1, "text": "SECTION 1\nAccessible doors."}],
    )

    artifact = index_module.build_index(
        pdf_file,
        output_file,
        source_name="Demo",
        source_url="https://example.com",
        document_id="TEST",
    )

    assert output_file.is_file()
    assert artifact["metadata"]["source_sha256"]
    assert artifact["metadata"]["total_chunks"] == 1
    assert artifact["chunks"][0]["chunk_id"] == "TEST-p001-c001"


def test_extract_pdf_reports_missing_source(tmp_path: Path) -> None:
    with pytest.raises(DataSourceError, match="not found"):
        extract_pdf_pages(tmp_path / "missing.pdf")


def test_extract_pdf_rejects_wrong_extension(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("not a PDF", encoding="utf-8")

    with pytest.raises(DataSourceError, match="extension"):
        extract_pdf_pages(source)
