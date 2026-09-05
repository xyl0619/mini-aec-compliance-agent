from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from mini_aec_agent.config import get_settings
from mini_aec_agent.reports import build_ifc_compliance_report, write_json_report

SAMPLE_IFC = Path(__file__).resolve().parents[1] / "examples" / "sample_office.ifc"


def test_report_can_check_selected_guid_and_write_json(tmp_path: Path) -> None:
    settings = replace(get_settings(), ifc_file=SAMPLE_IFC)
    full_report = build_ifc_compliance_report(settings=settings)
    failing = next(
        finding
        for finding in full_report["findings"]
        if finding.get("overall_status") == "FAIL"
    )

    report = build_ifc_compliance_report([failing["item"]["id"]], settings)
    output_file = write_json_report(report, tmp_path / "reports" / "report.json")
    saved = json.loads(output_file.read_text(encoding="utf-8"))

    assert report["summary"]["total"] == 1
    assert report["summary"]["FAIL"] == 1
    assert saved["report_id"] == report["report_id"]
    assert saved["findings"][0]["evidence"]["source_type"] == "IFC"


def test_report_requires_configured_ifc_model() -> None:
    settings = replace(get_settings(), ifc_file=None)

    with pytest.raises(ValueError, match="No IFC model"):
        build_ifc_compliance_report(settings=settings)


def test_report_deduplicates_ids_and_rejects_unsafe_batches() -> None:
    settings = replace(get_settings(), ifc_file=SAMPLE_IFC)
    full_report = build_ifc_compliance_report(settings=settings)
    global_id = full_report["findings"][0]["item"]["id"]

    deduplicated = build_ifc_compliance_report([global_id, global_id], settings)
    assert deduplicated["summary"]["total"] == 1

    with pytest.raises(ValueError, match="cannot be empty"):
        build_ifc_compliance_report([" "], settings)
    with pytest.raises(ValueError, match="at most"):
        build_ifc_compliance_report([global_id] * 501, settings)
