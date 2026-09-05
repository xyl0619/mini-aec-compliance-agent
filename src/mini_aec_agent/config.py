"""Environment-backed application settings."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from functools import lru_cache
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlsplit

from mini_aec_agent.exceptions import ConfigurationError

_SOURCE_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _discover_project_root() -> Path:
    explicit_root = os.getenv("MINI_AEC_PROJECT_ROOT")
    if explicit_root:
        return Path(explicit_root).expanduser().resolve()
    if (_SOURCE_PROJECT_ROOT / "pyproject.toml").is_file():
        return _SOURCE_PROJECT_ROOT
    working_directory = Path.cwd().resolve()
    if (working_directory / "pyproject.toml").is_file() and (
        working_directory / "data"
    ).is_dir():
        return working_directory
    return _SOURCE_PROJECT_ROOT


PROJECT_ROOT = _discover_project_root()


def _load_dotenv() -> None:
    """Load the repository .env file when python-dotenv is installed."""

    try:
        from dotenv import load_dotenv
    except ModuleNotFoundError:
        return

    load_dotenv(PROJECT_ROOT / ".env", override=False)


def _read_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        return int(raw_value)
    except ValueError as error:
        raise ConfigurationError(f"{name} must be an integer.") from error


def _read_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        return float(raw_value)
    except ValueError as error:
        raise ConfigurationError(f"{name} must be a number.") from error


def _read_bool(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{name} must be a boolean.")


def _read_retry_delays() -> tuple[float, ...]:
    raw_value = os.getenv("MINI_AEC_RETRY_DELAYS", "1,2,4")
    if not raw_value.strip():
        return ()

    try:
        delays = tuple(float(value.strip()) for value in raw_value.split(","))
    except ValueError as error:
        raise ConfigurationError(
            "MINI_AEC_RETRY_DELAYS must be a comma-separated list of numbers."
        ) from error

    if any(not math.isfinite(delay) for delay in delays):
        raise ConfigurationError("MINI_AEC_RETRY_DELAYS must contain finite numbers.")
    if any(delay < 0 for delay in delays):
        raise ConfigurationError("MINI_AEC_RETRY_DELAYS cannot contain negatives.")
    if len(delays) > 10 or any(delay > 60 for delay in delays):
        raise ConfigurationError(
            "MINI_AEC_RETRY_DELAYS allows at most 10 delays of at most 60 seconds."
        )

    return delays


def _read_path(name: str, default: Path) -> Path:
    return Path(os.getenv(name, str(default))).expanduser().resolve()


def _read_optional_path(name: str) -> Path | None:
    raw_value = os.getenv(name)
    if not raw_value:
        return None
    return Path(raw_value).expanduser().resolve()


def _is_unspecified_host(host: str) -> bool:
    try:
        return ip_address(host.strip("[]")).is_unspecified
    except ValueError:
        return False


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime configuration for data access and model orchestration."""

    project_root: Path
    building_file: Path
    regulations_file: Path
    ifc_file: Path | None
    ifc_rules_file: Path
    regulation_pdf_file: Path
    regulation_index_file: Path
    model_name: str
    model_temperature: float
    model_seed: int
    max_agent_steps: int
    max_output_tokens: int
    model_timeout_seconds: float
    retry_delays: tuple[float, ...]
    together_api_key: str | None
    log_level: str
    log_format: str
    api_host: str
    api_port: int
    service_api_key: str | None
    allow_insecure_public_bind: bool
    telemetry_enabled: bool
    otel_service_name: str
    otel_endpoint: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv()

        max_agent_steps = _read_int("MINI_AEC_MAX_AGENT_STEPS", 8)
        if not 1 <= max_agent_steps <= 32:
            raise ConfigurationError(
                "MINI_AEC_MAX_AGENT_STEPS must be between 1 and 32."
            )

        max_output_tokens = _read_int("MINI_AEC_MAX_OUTPUT_TOKENS", 1024)
        if not 1 <= max_output_tokens <= 8192:
            raise ConfigurationError(
                "MINI_AEC_MAX_OUTPUT_TOKENS must be between 1 and 8192."
            )

        model_timeout_seconds = _read_float("MINI_AEC_MODEL_TIMEOUT_SECONDS", 60)
        if (
            not math.isfinite(model_timeout_seconds)
            or not 1 <= model_timeout_seconds <= 300
        ):
            raise ConfigurationError(
                "MINI_AEC_MODEL_TIMEOUT_SECONDS must be between 1 and 300."
            )

        api_port = _read_int("MINI_AEC_API_PORT", 8000)
        if not 1 <= api_port <= 65535:
            raise ConfigurationError("MINI_AEC_API_PORT must be between 1 and 65535.")

        log_format = os.getenv("MINI_AEC_LOG_FORMAT", "text").lower()
        if log_format not in {"text", "json"}:
            raise ConfigurationError("MINI_AEC_LOG_FORMAT must be text or json.")

        log_level = os.getenv("MINI_AEC_LOG_LEVEL", "INFO").upper()
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ConfigurationError(
                "MINI_AEC_LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL."
            )

        model_name = os.getenv("MINI_AEC_MODEL", "Qwen/Qwen3.5-9B").strip()
        if not model_name or len(model_name) > 200:
            raise ConfigurationError("MINI_AEC_MODEL must be 1-200 characters.")

        model_temperature = _read_float("MINI_AEC_TEMPERATURE", 0.0)
        if not math.isfinite(model_temperature) or not 0 <= model_temperature <= 2:
            raise ConfigurationError("MINI_AEC_TEMPERATURE must be between 0 and 2.")

        api_host = os.getenv("MINI_AEC_API_HOST", "127.0.0.1").strip()
        if not api_host:
            raise ConfigurationError("MINI_AEC_API_HOST cannot be empty.")
        service_api_key = os.getenv("MINI_AEC_SERVICE_API_KEY") or None
        if service_api_key is not None and len(service_api_key) < 16:
            raise ConfigurationError(
                "MINI_AEC_SERVICE_API_KEY must contain at least 16 characters."
            )
        allow_insecure_public_bind = _read_bool(
            "MINI_AEC_ALLOW_INSECURE_PUBLIC_BIND", False
        )
        if (
            _is_unspecified_host(api_host)
            and service_api_key is None
            and not allow_insecure_public_bind
        ):
            raise ConfigurationError(
                "A public API bind requires MINI_AEC_SERVICE_API_KEY. Set "
                "MINI_AEC_ALLOW_INSECURE_PUBLIC_BIND=true only for an explicitly "
                "isolated environment."
            )

        otel_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or None
        if otel_endpoint is not None:
            parsed_endpoint = urlsplit(otel_endpoint)
            if (
                parsed_endpoint.scheme not in {"http", "https"}
                or not parsed_endpoint.netloc
            ):
                raise ConfigurationError(
                    "OTEL_EXPORTER_OTLP_ENDPOINT must be an absolute HTTP(S) URL."
                )

        otel_service_name = os.getenv(
            "OTEL_SERVICE_NAME", "mini-aec-compliance-agent"
        ).strip()
        if not otel_service_name or len(otel_service_name) > 128:
            raise ConfigurationError("OTEL_SERVICE_NAME must be 1-128 characters.")

        together_api_key = os.getenv("TOGETHER_API_KEY") or None
        if together_api_key is not None and not together_api_key.strip():
            together_api_key = None

        return cls(
            project_root=PROJECT_ROOT,
            building_file=_read_path(
                "MINI_AEC_BUILDING_FILE", PROJECT_ROOT / "data" / "building.json"
            ),
            regulations_file=_read_path(
                "MINI_AEC_REGULATIONS_FILE",
                PROJECT_ROOT / "data" / "regulations.json",
            ),
            ifc_file=_read_optional_path("MINI_AEC_IFC_FILE"),
            ifc_rules_file=_read_path(
                "MINI_AEC_IFC_RULES_FILE",
                PROJECT_ROOT / "data" / "rules" / "bfa_2025_accessibility.json",
            ),
            regulation_pdf_file=_read_path(
                "MINI_AEC_REGULATION_PDF",
                PROJECT_ROOT / "regulations" / "bfa_2008_2025.pdf",
            ),
            regulation_index_file=_read_path(
                "MINI_AEC_REGULATION_INDEX",
                PROJECT_ROOT / "data" / "processed" / "regulation_chunks.json",
            ),
            model_name=model_name,
            model_temperature=model_temperature,
            model_seed=_read_int("MINI_AEC_SEED", 42),
            max_agent_steps=max_agent_steps,
            max_output_tokens=max_output_tokens,
            model_timeout_seconds=model_timeout_seconds,
            retry_delays=_read_retry_delays(),
            together_api_key=together_api_key,
            log_level=log_level,
            log_format=log_format,
            api_host=api_host,
            api_port=api_port,
            service_api_key=service_api_key,
            allow_insecure_public_bind=allow_insecure_public_bind,
            telemetry_enabled=_read_bool("MINI_AEC_TELEMETRY_ENABLED", False),
            otel_service_name=otel_service_name,
            otel_endpoint=otel_endpoint,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return one immutable settings object per process."""

    return Settings.from_env()
