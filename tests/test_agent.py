from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import mini_aec_agent.agent as agent_module
from mini_aec_agent.agent import call_model, execute_tool, run_agent
from mini_aec_agent.config import get_settings
from mini_aec_agent.exceptions import ConfigurationError


class FakeToolCall:
    def __init__(self, call_id: str, name: str, arguments: str) -> None:
        self.id = call_id
        self.type = "function"
        self.function = SimpleNamespace(name=name, arguments=arguments)

    def model_dump(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "function": {
                "name": self.function.name,
                "arguments": self.function.arguments,
            },
        }


class FakeClient:
    def __init__(self, messages: list[Any], usages: list[Any] | None = None) -> None:
        self._messages = iter(messages)
        self._usages = iter(usages or [None for _ in messages])
        self.requests: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create_response)
        )

    def _create_response(self, **request: Any) -> Any:
        self.requests.append(request)
        message = next(self._messages)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message)], usage=next(self._usages)
        )


def test_agent_executes_tool_and_returns_trace() -> None:
    tool_call = FakeToolCall(
        "call-1", "check_item_compliance", '{"item_id": "Door-01"}'
    )
    client = FakeClient(
        [
            SimpleNamespace(content="", tool_calls=[tool_call]),
            SimpleNamespace(content="Door-01 fails.", tool_calls=None),
        ],
        usages=[
            SimpleNamespace(prompt_tokens=10, completion_tokens=2, total_tokens=12),
            {"prompt_tokens": 20, "completion_tokens": 3},
        ],
    )
    settings = replace(get_settings(), max_agent_steps=3, retry_delays=())

    result = run_agent(
        "Is Door-01 compliant?",
        return_trace=True,
        client=client,
        settings=settings,
    )

    assert isinstance(result, dict)
    assert result["answer"] == "Door-01 fails."
    assert result["steps"] == 2
    assert result["trace"][0]["tool"] == "check_item_compliance"
    assert result["trace"][0]["result"]["overall_status"] == "FAIL"
    assert result["metrics"]["model_calls"] == 2
    assert result["metrics"]["tool_calls"] == 1
    assert result["metrics"]["prompt_tokens"] == 30
    assert result["metrics"]["completion_tokens"] == 5
    assert result["metrics"]["total_tokens"] == 35
    assert result["metrics"]["duration_ms"] >= 0
    assert len(client.requests) == 2
    assert client.requests[0]["max_tokens"] == settings.max_output_tokens


def test_agent_records_invalid_tool_arguments() -> None:
    tool_call = FakeToolCall("call-1", "list_items", "not-json")
    client = FakeClient(
        [
            SimpleNamespace(content="", tool_calls=[tool_call]),
            SimpleNamespace(content="Unable to execute the tool.", tool_calls=None),
        ]
    )
    settings = replace(get_settings(), max_agent_steps=2, retry_delays=())

    result = run_agent(
        "List doors.", return_trace=True, client=client, settings=settings
    )

    assert isinstance(result, dict)
    assert "Invalid tool arguments" in result["trace"][0]["result"]["error"]


def test_execute_tool_validates_inputs() -> None:
    assert "error" in execute_tool("list_items", {})
    assert "error" in execute_tool("check_item_compliance", {"item_id": ""})
    assert "error" in execute_tool("unknown", {})
    assert "error" in execute_tool(
        "list_items", {"item_type": "door", "unexpected": True}
    )
    assert "error" in execute_tool("list_items", {"item_type": "unsupported"})
    assert "error" in execute_tool(
        "list_ifc_elements", {"ifc_class": "IfcDoor", "limit": True}
    )
    assert "error" in execute_tool(
        "list_ifc_elements", {"ifc_class": "IfcDoor", "limit": 501}
    )
    assert "error" in execute_tool(
        "list_ifc_elements", {"ifc_class": "IfcDoor;bad", "limit": 1}
    )


def test_json_tools_use_supplied_settings(tmp_path: Path) -> None:
    building_file = tmp_path / "building.json"
    building_file.write_text(
        json.dumps(
            {
                "components": [{"id": "Door-Custom", "type": "door", "width_mm": 1000}],
                "spaces": [],
            }
        ),
        encoding="utf-8",
    )
    settings = replace(get_settings(), building_file=building_file)

    listed = execute_tool("list_items", {"item_type": "door"}, settings)
    checked = execute_tool(
        "check_item_compliance", {"item_id": "Door-Custom"}, settings
    )

    assert [item["id"] for item in listed] == ["Door-Custom"]
    assert checked["item"]["id"] == "Door-Custom"


def test_call_model_retries_transient_errors(monkeypatch: Any) -> None:
    attempts = 0
    waits: list[float] = []

    def create(**request: Any) -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("temporary")
        return request["model"]

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    settings = replace(get_settings(), retry_delays=(0.1, 0.2))
    monkeypatch.setattr(agent_module, "_is_transient_api_error", lambda error: True)

    response = call_model(
        [{"role": "user", "content": "hello"}],
        client=client,
        settings=settings,
        sleep=waits.append,
    )

    assert response == settings.model_name
    assert attempts == 3
    assert waits == [0.1, 0.2]


def test_call_model_requires_api_key() -> None:
    settings = replace(get_settings(), together_api_key=None)

    try:
        call_model([], settings=settings)
    except ConfigurationError as error:
        assert "TOGETHER_API_KEY" in str(error)
    else:
        raise AssertionError("Expected a missing-key ConfigurationError.")


def test_agent_stops_at_configured_step_limit() -> None:
    tool_call = FakeToolCall("call-1", "list_items", '{"item_type": "door"}')
    client = FakeClient([SimpleNamespace(content="", tool_calls=[tool_call])])
    settings = replace(get_settings(), max_agent_steps=1, retry_delays=())

    result = run_agent(
        "List doors.", return_trace=True, client=client, settings=settings
    )

    assert isinstance(result, dict)
    assert "step limit" in result["answer"]
    assert result["steps"] == 1


def test_agent_rejects_empty_message() -> None:
    try:
        run_agent("  ")
    except ValueError as error:
        assert "cannot be empty" in str(error)
    else:
        raise AssertionError("Expected ValueError for an empty message.")


def test_agent_rejects_oversized_message() -> None:
    with pytest.raises(ValueError, match="cannot exceed"):
        run_agent("x" * 4001)


def test_agent_stops_excessive_parallel_tool_calls() -> None:
    tool_calls = [
        FakeToolCall(f"call-{index}", "list_items", '{"item_type":"door"}')
        for index in range(21)
    ]
    client = FakeClient([SimpleNamespace(content="", tool_calls=tool_calls)])

    result = run_agent("List doors.", return_trace=True, client=client)

    assert isinstance(result, dict)
    assert "too many tools" in result["answer"]
    assert result["metrics"]["tool_calls"] == 0


def test_agent_rejects_oversized_tool_arguments() -> None:
    tool_call = FakeToolCall("call-1", "list_items", "{" + "x" * 20_001 + "}")
    client = FakeClient(
        [
            SimpleNamespace(content="", tool_calls=[tool_call]),
            SimpleNamespace(content="Rejected unsafe arguments.", tool_calls=None),
        ]
    )
    settings = replace(get_settings(), max_agent_steps=2, retry_delays=())

    result = run_agent(
        "List doors.", return_trace=True, client=client, settings=settings
    )

    assert isinstance(result, dict)
    assert "exceed" in result["trace"][0]["result"]["error"]


def test_agent_bounds_tool_results(monkeypatch: pytest.MonkeyPatch) -> None:
    tool_call = FakeToolCall("call-1", "list_items", '{"item_type":"door"}')
    client = FakeClient(
        [
            SimpleNamespace(content="", tool_calls=[tool_call]),
            SimpleNamespace(content="Narrowed.", tool_calls=None),
        ]
    )
    monkeypatch.setattr(
        agent_module, "execute_tool", lambda *args: {"data": "x" * 30_000}
    )

    result = run_agent("List doors.", return_trace=True, client=client)

    assert isinstance(result, dict)
    assert "safety limit" in result["trace"][0]["result"]["error"]


def test_agent_bounds_cumulative_tool_transcript(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool_calls = [
        FakeToolCall(f"call-{index}", "list_items", '{"item_type":"door"}')
        for index in range(11)
    ]
    client = FakeClient([SimpleNamespace(content="", tool_calls=tool_calls)])
    monkeypatch.setattr(
        agent_module, "execute_tool", lambda *args: {"data": "x" * 24_000}
    )

    result = run_agent("List doors.", return_trace=True, client=client)

    assert isinstance(result, dict)
    assert "cumulative tool output" in result["answer"]
    assert result["metrics"]["tool_calls"] == 11


def test_agent_does_not_expose_tool_exception_details(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    tool_call = FakeToolCall("call-1", "list_items", '{"item_type":"door"}')
    client = FakeClient(
        [
            SimpleNamespace(content="", tool_calls=[tool_call]),
            SimpleNamespace(content="Handled.", tool_calls=None),
        ]
    )

    def fail(*args: Any) -> None:
        raise RuntimeError("sensitive local detail")

    monkeypatch.setattr(agent_module, "execute_tool", fail)
    result = run_agent("List doors.", return_trace=True, client=client)

    assert isinstance(result, dict)
    error = result["trace"][0]["result"]["error"]
    assert error == "Tool execution failed: RuntimeError."
    assert "sensitive" not in error
    assert "sensitive" not in caplog.text


def test_agent_stops_on_malformed_model_tool_call() -> None:
    tool_call = FakeToolCall("call-1", "list_items", '{"item_type":"door"}')
    tool_call.function.arguments = None
    client = FakeClient([SimpleNamespace(content="", tool_calls=[tool_call])])

    result = run_agent("List doors.", return_trace=True, client=client)

    assert isinstance(result, dict)
    assert "malformed tool call" in result["answer"]


def test_agent_ignores_invalid_usage_values() -> None:
    client = FakeClient(
        [SimpleNamespace(content="Done.", tool_calls=None)],
        usages=[{"prompt_tokens": "invalid", "completion_tokens": float("nan")}],
    )

    result = run_agent("Check.", return_trace=True, client=client)

    assert isinstance(result, dict)
    assert result["metrics"]["total_tokens"] == 0
