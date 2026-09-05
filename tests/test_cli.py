from __future__ import annotations

import pytest

import mini_aec_agent.cli as cli


def test_one_shot_cli_prints_answer(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        cli, "run_agent", lambda question, return_trace, settings: "PASS"
    )

    exit_code = cli.main(["--question", "Check Door-02", "--log-level", "ERROR"])

    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "PASS"


def test_one_shot_cli_can_print_trace(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        cli,
        "run_agent",
        lambda question, return_trace, settings: {
            "answer": "FAIL",
            "trace": [{"tool": "check_item_compliance"}],
            "steps": 2,
        },
    )

    exit_code = cli.main(["--question", "Check Door-01", "--trace"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "FAIL" in output
    assert '"tool": "check_item_compliance"' in output


def test_interactive_cli_exits_cleanly(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("builtins.input", lambda prompt: "exit")

    exit_code = cli.main([])

    assert exit_code == 0
    assert "Goodbye!" in capsys.readouterr().out


def test_cli_handles_validation_and_unexpected_failures(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def invalid(*args, **kwargs):
        raise ValueError("bad question")

    monkeypatch.setattr(cli, "run_agent", invalid)
    assert cli.main(["--question", "bad"]) == 2

    def unexpected(*args, **kwargs):
        raise RuntimeError("sensitive detail")

    monkeypatch.setattr(cli, "run_agent", unexpected)
    assert cli.main(["--question", "bad"]) == 1
    assert "sensitive detail" not in caplog.text
