from __future__ import annotations

import asyncio
import importlib
import json
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from mini_aec_agent.api import create_app
from mini_aec_agent.config import get_settings

SAMPLE_IFC = Path(__file__).resolve().parents[1] / "examples" / "sample_office.ifc"


def _settings(tmp_path: Path):
    index_file = tmp_path / "index.json"
    index_file.write_text(
        json.dumps(
            {
                "chunks": [
                    {
                        "chunk_id": "BFA2025-p066-c001",
                        "document_id": "BFA2025",
                        "source": "BFA 2025",
                        "source_url": "https://example.com/bfa.pdf",
                        "pdf_page": 66,
                        "text": "Doors on accessible routes need 800 mm clear width.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return replace(
        get_settings(),
        ifc_file=SAMPLE_IFC,
        regulation_index_file=index_file,
    )


def test_health_and_system_endpoints(tmp_path: Path) -> None:
    client = TestClient(create_app(_settings(tmp_path)))

    health = client.get("/health")
    system = client.get("/v1/system")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert system.json()["ifc_configured"] is True
    assert system.json()["regulation_index_configured"] is True
    assert system.json()["api_key_auth_enabled"] is False
    assert system.json()["telemetry_enabled"] is False


def test_ifc_query_and_compliance_endpoints(tmp_path: Path) -> None:
    client = TestClient(create_app(_settings(tmp_path)))

    summary = client.get("/v1/ifc/summary")
    doors = client.get("/v1/ifc/elements", params={"ifc_class": "IfcDoor", "limit": 2})
    global_id = doors.json()["elements"][0]["global_id"]
    element = client.get(f"/v1/ifc/elements/{global_id}")
    check = client.post("/v1/ifc/checks", json={"global_id": global_id})

    assert summary.json()["class_counts"]["IfcDoor"] == 3
    assert doors.json()["returned"] == 2
    assert element.json()["name"] == "Door-01"
    assert check.json()["overall_status"] == "FAIL"
    assert check.json()["checks"][0]["source"]["pdf_page"] == 66


def test_regulation_search_endpoint_returns_citation(tmp_path: Path) -> None:
    client = TestClient(create_app(_settings(tmp_path)))

    response = client.post(
        "/v1/regulations/search", json={"query": "accessible door width", "top_k": 1}
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["citation"] == "BFA 2025, PDF p.66"


def test_report_endpoint_checks_all_ifc_doors(tmp_path: Path) -> None:
    client = TestClient(create_app(_settings(tmp_path)))

    response = client.post("/v1/reports/ifc-compliance", json={})
    report = response.json()

    assert response.status_code == 200
    assert report["summary"] == {
        "total": 3,
        "PASS": 2,
        "FAIL": 1,
        "UNKNOWN": 0,
        "ERROR": 0,
    }
    assert report["rule_catalog"]["catalog_id"] == "hk-bfa-2008-2025-accessibility"


def test_agent_endpoint_supports_mocked_offline_run(
    tmp_path: Path, monkeypatch
) -> None:
    api_module = importlib.import_module("mini_aec_agent.api.app")
    monkeypatch.setattr(
        api_module,
        "run_agent",
        lambda question, return_trace, settings: {
            "answer": "mock answer",
            "trace": [],
            "steps": 1,
            "metrics": {
                "model_calls": 1,
                "tool_calls": 0,
                "prompt_tokens": 10,
                "completion_tokens": 2,
                "total_tokens": 12,
                "duration_ms": 1.5,
            },
        },
    )
    client = TestClient(api_module.create_app(_settings(tmp_path)))

    response = client.post(
        "/v1/agent/runs", json={"question": "Check the IFC", "include_trace": True}
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "mock answer"
    assert response.json()["metrics"]["total_tokens"] == 12

    without_trace = client.post("/v1/agent/runs", json={"question": "Check the IFC"})
    assert "trace" not in without_trace.json()
    assert without_trace.json()["metrics"]["duration_ms"] == 1.5


def test_optional_api_key_protects_v1_but_not_health(tmp_path: Path) -> None:
    settings = replace(_settings(tmp_path), service_api_key="correct-secret-value")
    client = TestClient(create_app(settings))

    health = client.get("/health")
    missing_key = client.get("/v1/system")
    wrong_key = client.get("/v1/system", headers={"X-API-Key": "wrong"})
    authorized = client.get("/v1/system", headers={"X-API-Key": "correct-secret-value"})

    assert health.status_code == 200
    assert missing_key.status_code == 401
    assert wrong_key.status_code == 401
    assert authorized.status_code == 200
    assert authorized.json()["api_key_auth_enabled"] is True


def test_api_sets_security_headers_and_limits_request_size(tmp_path: Path) -> None:
    client = TestClient(create_app(_settings(tmp_path)))

    health = client.get("/health")
    system = client.get("/v1/system")
    oversized = client.post(
        "/v1/agent/runs",
        content=b"x" * (1024 * 1024 + 1),
        headers={"content-type": "application/json"},
    )

    assert health.headers["x-content-type-options"] == "nosniff"
    assert health.headers["x-frame-options"] == "DENY"
    assert "cache-control" not in health.headers
    assert system.headers["cache-control"] == "no-store"
    assert oversized.status_code == 413
    assert oversized.headers["x-content-type-options"] == "nosniff"


def test_api_limits_chunked_body_without_content_length(tmp_path: Path) -> None:
    application = create_app(_settings(tmp_path))
    request_messages = iter(
        [
            {"type": "http.request", "body": b"x" * 600_000, "more_body": True},
            {"type": "http.request", "body": b"x" * 600_000, "more_body": False},
        ]
    )
    response_messages: list[dict] = []

    async def receive() -> dict:
        return next(request_messages)

    async def send(message: dict) -> None:
        response_messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/v1/agent/runs",
        "raw_path": b"/v1/agent/runs",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "root_path": "",
    }

    asyncio.run(application(scope, receive, send))

    start = next(
        message
        for message in response_messages
        if message["type"] == "http.response.start"
    )
    headers = dict(start["headers"])
    assert start["status"] == 413
    assert headers[b"cache-control"] == b"no-store"


def test_ifc_path_rejects_invalid_guid_shape(tmp_path: Path) -> None:
    client = TestClient(create_app(_settings(tmp_path)))

    assert client.get("/v1/ifc/elements/not-a-guid").status_code == 422
    assert client.get("/v1/ifc/elements/!!!!!!!!!!!!!!!!!!!!!!").status_code == 422
    assert client.post("/v1/ifc/checks", json={"global_id": "bad"}).status_code == 422
    assert (
        client.post(
            "/v1/reports/ifc-compliance", json={"global_ids": ["bad"]}
        ).status_code
        == 422
    )


def test_ifc_class_rejects_non_identifier_input(tmp_path: Path) -> None:
    client = TestClient(create_app(_settings(tmp_path)))

    response = client.get("/v1/ifc/elements", params={"ifc_class": "IfcDoor;DROP"})

    assert response.status_code == 422


def test_api_returns_project_errors_as_bad_requests(tmp_path: Path) -> None:
    settings = replace(_settings(tmp_path), ifc_file=None)
    client = TestClient(create_app(settings))

    response = client.get("/v1/ifc/summary")

    assert response.status_code == 400
    assert "No IFC model" in response.json()["detail"]


def test_api_redacts_unexpected_error_details(tmp_path: Path, monkeypatch) -> None:
    api_module = importlib.import_module("mini_aec_agent.api.app")

    def fail(*args, **kwargs):
        raise RuntimeError("sensitive internal detail")

    monkeypatch.setattr(api_module, "run_agent", fail)
    client = TestClient(
        api_module.create_app(_settings(tmp_path)), raise_server_exceptions=False
    )

    response = client.post("/v1/agent/runs", json={"question": "fail safely"})

    assert response.status_code == 500
    assert response.json() == {"detail": "An internal error occurred."}
    assert "sensitive" not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_api_request_validation_rejects_bad_payload(tmp_path: Path) -> None:
    client = TestClient(create_app(_settings(tmp_path)))

    response = client.post(
        "/v1/regulations/search", json={"query": "", "unexpected": True}
    )

    assert response.status_code == 422
