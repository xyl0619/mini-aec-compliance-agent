"""Evidence-bearing compliance report generation."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from mini_aec_agent.config import Settings, get_settings
from mini_aec_agent.ifc import IFCComplianceService, IFCModelService
from mini_aec_agent.io_utils import atomic_write_text
from mini_aec_agent.repository import JsonAECRepository


def build_ifc_compliance_report(
    global_ids: list[str] | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Check selected IFC elements, or all doors, and aggregate their statuses."""

    active_settings = settings or get_settings()
    if active_settings.ifc_file is None:
        raise ValueError("No IFC model is configured for report generation.")

    ifc_service = IFCModelService(active_settings.ifc_file)
    rule_settings = replace(
        active_settings, regulations_file=active_settings.ifc_rules_file
    )
    repository = JsonAECRepository(rule_settings)
    compliance_service = IFCComplianceService(ifc_service, repository)

    if global_ids is None:
        door_query = ifc_service.list_elements("IfcDoor", limit=500)
        elements = cast(list[dict[str, Any]], door_query["elements"])
        global_ids = [
            str(element["global_id"])
            for element in elements
            if isinstance(element, dict) and element.get("global_id")
        ]

    if len(global_ids) > IFCModelService.MAX_QUERY_LIMIT:
        raise ValueError(
            f"A report can contain at most {IFCModelService.MAX_QUERY_LIMIT} elements."
        )
    normalized_ids = list(dict.fromkeys(global_id.strip() for global_id in global_ids))
    if any(not global_id for global_id in normalized_ids):
        raise ValueError("Report GlobalIds cannot be empty.")

    findings = [
        compliance_service.check_element(global_id) for global_id in normalized_ids
    ]
    counts = dict.fromkeys(("PASS", "FAIL", "UNKNOWN", "ERROR"), 0)
    for finding in findings:
        status = finding.get("overall_status")
        if status in counts:
            counts[status] += 1
        else:
            counts["ERROR"] += 1

    catalog = repository.load_regulations()
    return {
        "report_id": str(uuid4()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "report_type": "ifc_compliance",
        "model": ifc_service.summary(),
        "rule_catalog": {
            "catalog_id": catalog["catalog_id"],
            "title": catalog["title"],
            "version": catalog["version"],
            "jurisdiction": catalog["jurisdiction"],
            "status": catalog["status"],
        },
        "summary": {"total": len(findings), **counts},
        "findings": findings,
        "disclaimer": (
            "Prototype output. Verify source clauses and model measurements before "
            "professional or legal use."
        ),
    }


def write_json_report(report: dict[str, Any], output_file: str | Path) -> Path:
    """Write one report as UTF-8 JSON and return its resolved path."""

    output_path = atomic_write_text(
        output_file,
        json.dumps(report, indent=2, ensure_ascii=False),
    )
    return output_path
