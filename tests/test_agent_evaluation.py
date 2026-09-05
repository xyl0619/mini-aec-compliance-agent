from __future__ import annotations

import json
from pathlib import Path

import pytest

import evaluation.evaluate_agent as evaluation
from mini_aec_agent.exceptions import DataSourceError


def test_agent_evaluation_rejects_invalid_case_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases_file = tmp_path / "cases.json"
    cases_file.write_text('{"not":"a list"}', encoding="utf-8")
    monkeypatch.setattr(evaluation, "TEST_CASES_FILE", cases_file)

    with pytest.raises(DataSourceError):
        evaluation.load_test_cases()

    cases_file.write_text(
        '[{"id":"case","question":"ok","expected_statuses":{"Door":"MAYBE"}}]',
        encoding="utf-8",
    )
    with pytest.raises(DataSourceError):
        evaluation.load_test_cases()


def test_agent_evaluation_detects_step_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        evaluation,
        "run_agent",
        lambda question, return_trace: {
            "answer": "The agent stopped after reaching the configured step limit.",
            "trace": [],
            "steps": evaluation.MAX_AGENT_STEPS,
            "metrics": {"total_tokens": 10, "duration_ms": 1.0},
        },
    )

    result = evaluation.evaluate_case({"id": "limit", "question": "test"})

    assert result["outcome"] == "FAIL"
    assert any("step limit" in error for error in result["errors"])


def test_agent_evaluation_saves_operational_metrics_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_file = tmp_path / "nested" / "results.json"
    monkeypatch.setattr(evaluation, "RESULTS_FILE", output_file)
    results = [
        {
            "outcome": "PASS",
            "tool_calls": 1,
            "steps": 2,
            "metrics": {"total_tokens": 40, "duration_ms": 20.0},
        }
    ]

    output = evaluation.save_results(results)
    saved = json.loads(output_file.read_text(encoding="utf-8"))

    assert output["summary"]["average_tokens_per_evaluable_case"] == 40
    assert saved["summary"]["average_duration_ms_per_evaluable_case"] == 20.0
