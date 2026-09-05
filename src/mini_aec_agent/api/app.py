"""HTTP API for agent, IFC, regulation, and report workflows."""

from __future__ import annotations

import logging
import secrets
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Path, Query, status
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, Field
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mini_aec_agent import __version__
from mini_aec_agent.agent import run_agent
from mini_aec_agent.config import Settings, get_settings
from mini_aec_agent.exceptions import MiniAECError
from mini_aec_agent.ifc_tools import (
    check_ifc_element_compliance,
    get_ifc_element,
    get_ifc_summary,
    list_ifc_elements,
)
from mini_aec_agent.observability import instrument_fastapi
from mini_aec_agent.regulation_tools import retrieve_regulations
from mini_aec_agent.reports import build_ifc_compliance_report

logger = logging.getLogger(__name__)
_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
MAX_REQUEST_BODY_BYTES = 1024 * 1024
MAX_REQUEST_BODY_MESSAGES = 1024
IFC_GUID_PATTERN = r"^[0-9A-Za-z_$]{22}$"
IFCGlobalId = Annotated[
    str,
    Field(min_length=22, max_length=22, pattern=IFC_GUID_PATTERN),
]


def _security_header_values(request_path: str) -> dict[str, str]:
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
    }
    if request_path.startswith("/v1"):
        headers["Cache-Control"] = "no-store"
    return headers


class RequestBodyLimitMiddleware:
    """Enforce the request limit for declared and streaming HTTP bodies."""

    def __init__(self, app: ASGIApp, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_path = str(scope.get("path", ""))
        content_length_values = [
            value.decode("latin-1")
            for name, value in scope.get("headers", [])
            if name.lower() == b"content-length"
        ]
        if len(content_length_values) > 1:
            await self._send_error(
                scope,
                receive,
                send,
                request_path,
                400,
                "Invalid Content-Length header.",
            )
            return
        raw_content_length = content_length_values[0] if content_length_values else None
        if raw_content_length is not None:
            try:
                content_length = int(raw_content_length)
            except ValueError:
                await self._send_error(
                    scope,
                    receive,
                    send,
                    request_path,
                    400,
                    "Invalid Content-Length header.",
                )
                return
            if content_length < 0:
                await self._send_error(
                    scope,
                    receive,
                    send,
                    request_path,
                    400,
                    "Invalid Content-Length header.",
                )
                return
            if content_length > self.max_body_bytes:
                await self._send_error(
                    scope,
                    receive,
                    send,
                    request_path,
                    413,
                    "Request body is too large.",
                )
                return

        received_bytes = 0
        request_messages: list[Message] = []
        while True:
            message = await receive()
            request_messages.append(message)
            if len(request_messages) > MAX_REQUEST_BODY_MESSAGES:
                await self._send_error(
                    scope,
                    receive,
                    send,
                    request_path,
                    413,
                    "Request body is too fragmented.",
                )
                return
            if message["type"] == "http.disconnect":
                break
            if message["type"] != "http.request":
                continue
            received_bytes += len(message.get("body", b""))
            if received_bytes > self.max_body_bytes:
                await self._send_error(
                    scope,
                    receive,
                    send,
                    request_path,
                    413,
                    "Request body is too large.",
                )
                return
            if not message.get("more_body", False):
                break

        buffered_messages = iter(request_messages)

        async def buffered_receive() -> Message:
            return next(buffered_messages, {"type": "http.disconnect"})

        async def secured_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                for name, value in _security_header_values(request_path).items():
                    response_headers[name] = value
            await send(message)

        await self.app(scope, buffered_receive, secured_send)

    @staticmethod
    async def _send_error(
        scope: Scope,
        receive: Receive,
        send: Send,
        request_path: str,
        status_code: int,
        detail: str,
    ) -> None:
        response = JSONResponse(
            status_code=status_code,
            content={"detail": detail},
            headers=_security_header_values(request_path),
        )
        await response(scope, receive, send)


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentRunRequest(StrictRequest):
    question: str = Field(min_length=1, max_length=4000)
    include_trace: bool = False


class RegulationSearchRequest(StrictRequest):
    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)


class IFCCheckRequest(StrictRequest):
    global_id: IFCGlobalId


class IFCReportRequest(StrictRequest):
    global_ids: list[IFCGlobalId] | None = Field(default=None, max_length=500)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an application with immutable settings for easy testing."""

    active_settings = settings or get_settings()
    app = FastAPI(
        title="Mini AEC Compliance Agent API",
        version=__version__,
        description=(
            "Inspectable AEC agent, IFC query, regulation retrieval, and "
            "deterministic compliance endpoints."
        ),
    )
    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_body_bytes=MAX_REQUEST_BODY_BYTES,
    )

    def require_api_key(
        supplied_key: Annotated[str | None, Depends(_API_KEY_HEADER)],
    ) -> None:
        expected_key = active_settings.service_api_key
        if expected_key is None:
            return
        supplied_bytes = (supplied_key or "").encode("utf-8")
        if not secrets.compare_digest(supplied_bytes, expected_key.encode("utf-8")):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing API key.",
                headers={"WWW-Authenticate": "ApiKey"},
            )

    protected = [Depends(require_api_key)]

    @app.exception_handler(MiniAECError)
    async def handle_project_error(request: Any, error: MiniAECError) -> JSONResponse:
        logger.warning("Project request failed: %s", type(error).__name__)
        return JSONResponse(
            status_code=400,
            content={
                "detail": "The configured project data could not be processed.",
                "error_type": type(error).__name__,
            },
            headers=_security_header_values(str(request.url.path)),
        )

    @app.exception_handler(ValueError)
    async def handle_value_error(request: Any, error: ValueError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": str(error)},
            headers=_security_header_values(str(request.url.path)),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Any, error: Exception) -> JSONResponse:
        logger.error("Unexpected API failure: %s", type(error).__name__)
        return JSONResponse(
            status_code=500,
            content={"detail": "An internal error occurred."},
            headers=_security_header_values(str(request.url.path)),
        )

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/v1/system", tags=["system"], dependencies=protected)
    def system() -> dict[str, Any]:
        return {
            "version": __version__,
            "model": active_settings.model_name,
            "ifc_configured": active_settings.ifc_file is not None,
            "regulation_index_configured": (
                active_settings.regulation_index_file.is_file()
            ),
            "api_key_auth_enabled": active_settings.service_api_key is not None,
            "telemetry_enabled": active_settings.telemetry_enabled,
            "max_agent_steps": active_settings.max_agent_steps,
            "max_output_tokens": active_settings.max_output_tokens,
        }

    @app.post("/v1/agent/runs", tags=["agent"], dependencies=protected)
    def agent_run(payload: AgentRunRequest) -> dict[str, Any]:
        result = run_agent(
            payload.question,
            return_trace=True,
            settings=active_settings,
        )
        if not isinstance(result, dict):
            return {"answer": result}

        response = dict(result)
        if not payload.include_trace:
            response.pop("trace", None)
        return response

    @app.get("/v1/ifc/summary", tags=["ifc"], dependencies=protected)
    def ifc_summary() -> dict[str, Any]:
        return get_ifc_summary(active_settings)

    @app.get("/v1/ifc/elements", tags=["ifc"], dependencies=protected)
    def ifc_elements(
        ifc_class: str = Query(
            ..., min_length=3, max_length=64, pattern=r"^Ifc[A-Za-z0-9]{0,61}$"
        ),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict[str, Any]:
        return list_ifc_elements(ifc_class, limit, active_settings)

    @app.get("/v1/ifc/elements/{global_id}", tags=["ifc"], dependencies=protected)
    def ifc_element(
        global_id: str = Path(
            ..., min_length=22, max_length=22, pattern=IFC_GUID_PATTERN
        ),
    ) -> dict[str, Any]:
        return get_ifc_element(global_id, active_settings)

    @app.post("/v1/ifc/checks", tags=["ifc"], dependencies=protected)
    def ifc_check(payload: IFCCheckRequest) -> dict[str, Any]:
        return check_ifc_element_compliance(payload.global_id, active_settings)

    @app.post("/v1/regulations/search", tags=["regulations"], dependencies=protected)
    def regulation_search(payload: RegulationSearchRequest) -> dict[str, Any]:
        return retrieve_regulations(payload.query, payload.top_k, active_settings)

    @app.post("/v1/reports/ifc-compliance", tags=["reports"], dependencies=protected)
    def ifc_report(payload: IFCReportRequest) -> dict[str, Any]:
        return build_ifc_compliance_report(payload.global_ids, active_settings)

    instrument_fastapi(app, active_settings)
    return app


app = create_app()


def run() -> None:
    """Run the development server through the project console script."""

    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "mini_aec_agent.api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )
