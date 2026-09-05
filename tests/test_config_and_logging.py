from __future__ import annotations

import json
import logging

import pytest

from mini_aec_agent.config import Settings
from mini_aec_agent.exceptions import ConfigurationError
from mini_aec_agent.logging_config import configure_logging


def test_settings_read_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_service_key = "test-service-key-1234"  # pragma: allowlist secret
    monkeypatch.setenv("MINI_AEC_MODEL", "test/model")
    monkeypatch.setenv("MINI_AEC_MAX_AGENT_STEPS", "4")
    monkeypatch.setenv("MINI_AEC_RETRY_DELAYS", "0,0.5")
    monkeypatch.setenv("MINI_AEC_LOG_FORMAT", "json")
    monkeypatch.setenv("MINI_AEC_SERVICE_API_KEY", fake_service_key)
    monkeypatch.setenv("MINI_AEC_TELEMETRY_ENABLED", "yes")

    settings = Settings.from_env()

    assert settings.model_name == "test/model"
    assert settings.max_agent_steps == 4
    assert settings.retry_delays == (0.0, 0.5)
    assert settings.log_format == "json"
    assert settings.service_api_key == fake_service_key
    assert settings.telemetry_enabled is True


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("MINI_AEC_MAX_AGENT_STEPS", "zero", "must be an integer"),
        ("MINI_AEC_TEMPERATURE", "cold", "must be a number"),
        ("MINI_AEC_RETRY_DELAYS", "soon", "comma-separated"),
        ("MINI_AEC_RETRY_DELAYS", "-1", "cannot contain negatives"),
        ("MINI_AEC_LOG_FORMAT", "yaml", "must be text or json"),
        ("MINI_AEC_TELEMETRY_ENABLED", "perhaps", "must be a boolean"),
    ],
)
def test_settings_reject_invalid_values(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str, message: str
) -> None:
    monkeypatch.setenv(name, value)

    with pytest.raises(ConfigurationError, match=message):
        Settings.from_env()


def test_settings_reject_non_positive_step_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MINI_AEC_MAX_AGENT_STEPS", "0")

    with pytest.raises(ConfigurationError, match="between 1 and 32"):
        Settings.from_env()


def test_settings_allows_disabling_application_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MINI_AEC_RETRY_DELAYS", " ")

    assert Settings.from_env().retry_delays == ()


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("MINI_AEC_MAX_AGENT_STEPS", "33", "between 1 and 32"),
        ("MINI_AEC_MAX_OUTPUT_TOKENS", "0", "between 1 and 8192"),
        ("MINI_AEC_MODEL_TIMEOUT_SECONDS", "301", "between 1 and 300"),
        ("MINI_AEC_TEMPERATURE", "3", "between 0 and 2"),
        ("MINI_AEC_RETRY_DELAYS", "61", "at most 60 seconds"),
        ("MINI_AEC_RETRY_DELAYS", "nan", "finite numbers"),
        ("MINI_AEC_LOG_LEVEL", "TRACE", "must be DEBUG"),
        ("MINI_AEC_SERVICE_API_KEY", "short", "at least 16"),
        ("OTEL_EXPORTER_OTLP_ENDPOINT", "file:///tmp/traces", "HTTP\\(S\\)"),
        ("OTEL_SERVICE_NAME", " ", "must be 1-128"),
    ],
)
def test_settings_reject_unsafe_bounds(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str, message: str
) -> None:
    monkeypatch.setenv(name, value)

    with pytest.raises(ConfigurationError, match=message):
        Settings.from_env()


def test_public_bind_requires_key_or_explicit_escape_hatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MINI_AEC_API_HOST", "0.0.0.0")
    monkeypatch.delenv("MINI_AEC_SERVICE_API_KEY", raising=False)

    with pytest.raises(ConfigurationError, match="public API bind"):
        Settings.from_env()

    monkeypatch.setenv("MINI_AEC_ALLOW_INSECURE_PUBLIC_BIND", "true")
    assert Settings.from_env().allow_insecure_public_bind is True


def test_expanded_unspecified_ipv6_bind_requires_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MINI_AEC_API_HOST", "0:0:0:0:0:0:0:0")
    monkeypatch.delenv("MINI_AEC_SERVICE_API_KEY", raising=False)

    with pytest.raises(ConfigurationError, match="public API bind"):
        Settings.from_env()


@pytest.mark.parametrize("port", ["0", "65536"])
def test_settings_reject_invalid_api_port(
    monkeypatch: pytest.MonkeyPatch, port: str
) -> None:
    monkeypatch.setenv("MINI_AEC_API_PORT", port)

    with pytest.raises(ConfigurationError, match="between 1 and 65535"):
        Settings.from_env()


def test_json_logging_emits_structured_record(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("INFO", "json")

    logging.getLogger("tests.logging").info("structured message")

    payload = json.loads(capsys.readouterr().err)
    assert payload["level"] == "INFO"
    assert payload["logger"] == "tests.logging"
    assert payload["message"] == "structured message"
