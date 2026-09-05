"""Agent-facing IFC query tools."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from mini_aec_agent.config import Settings, get_settings
from mini_aec_agent.ifc import IFCComplianceService, IFCModelService
from mini_aec_agent.repository import JsonAECRepository


def _service(settings: Settings | None = None) -> IFCModelService:
    active_settings = settings or get_settings()
    if active_settings.ifc_file is None:
        raise ValueError(
            "No IFC model is configured. Set MINI_AEC_IFC_FILE or use --ifc."
        )
    return IFCModelService(active_settings.ifc_file)


def get_ifc_summary(settings: Settings | None = None) -> dict[str, Any]:
    """Return schema, project metadata, and common IFC entity counts."""

    return _service(settings).summary()


def list_ifc_elements(
    ifc_class: str, limit: int = 100, settings: Settings | None = None
) -> dict[str, Any]:
    """List JSON-safe IFC elements of one class."""

    return _service(settings).list_elements(ifc_class, limit)


def get_ifc_element(global_id: str, settings: Settings | None = None) -> dict[str, Any]:
    """Return one IFC element by its stable GlobalId."""

    return _service(settings).get_element(global_id)


def check_ifc_element_compliance(
    global_id: str, settings: Settings | None = None
) -> dict[str, Any]:
    """Check one supported IFC element and retain its source evidence."""

    service = _service(settings)
    active_settings = settings or get_settings()
    ifc_rule_settings = replace(
        active_settings, regulations_file=active_settings.ifc_rules_file
    )
    repository = JsonAECRepository(ifc_rule_settings)
    return IFCComplianceService(service, repository).check_element(global_id)
