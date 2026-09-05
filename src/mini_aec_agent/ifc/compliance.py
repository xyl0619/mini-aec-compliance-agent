"""Adapt IFC elements to the deterministic compliance domain model."""

from __future__ import annotations

from typing import Any

from mini_aec_agent.compliance import ComplianceEngine
from mini_aec_agent.ifc.service import IFCModelService
from mini_aec_agent.repository import JsonAECRepository

IFC_TYPE_MAP = {"IfcDoor": "door"}


class IFCComplianceService:
    """Evaluate supported IFC elements while preserving source provenance."""

    def __init__(
        self,
        ifc_service: IFCModelService,
        repository: JsonAECRepository | None = None,
    ) -> None:
        self.ifc_service = ifc_service
        self.engine = ComplianceEngine(repository)

    def check_element(self, global_id: str) -> dict[str, Any]:
        record = self.ifc_service.get_element(global_id)
        if "error" in record:
            return record

        ifc_class = str(record["ifc_class"])
        item_type = IFC_TYPE_MAP.get(ifc_class)
        if item_type is None:
            return {
                "item": record,
                "overall_status": "UNKNOWN",
                "checks": [],
                "reason": f"No compliance adapter exists for {ifc_class}.",
                "evidence": self._evidence(record),
            }

        container = record.get("container")
        location = container.get("name") if isinstance(container, dict) else None
        normalized_item: dict[str, Any] = {
            "id": record["global_id"],
            "name": record.get("name"),
            "type": item_type,
            "location": location,
        }

        if "clear_width_mm" in record:
            normalized_item["width_mm"] = record["clear_width_mm"]
        if "on_accessible_route" in record:
            normalized_item["on_accessible_route"] = record["on_accessible_route"]

        result = self.engine.evaluate_item(normalized_item)
        result["evidence"] = self._evidence(record)
        return result

    def _evidence(self, record: dict[str, Any]) -> dict[str, Any]:
        source_fields: dict[str, str] = {}
        clear_width_source = record.get("clear_width_source")
        if "clear_width_mm" in record and isinstance(clear_width_source, str):
            source_fields["width_mm"] = clear_width_source
        accessible_route_source = record.get("accessible_route_source")
        if isinstance(accessible_route_source, str):
            source_fields["applicability"] = accessible_route_source
        return {
            "source_type": "IFC",
            "source_file": self.ifc_service.file_path.name,
            "global_id": record.get("global_id"),
            "ifc_class": record.get("ifc_class"),
            "source_fields": source_fields,
        }
