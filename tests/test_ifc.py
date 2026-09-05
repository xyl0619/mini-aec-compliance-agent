from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from mini_aec_agent.agent import execute_tool
from mini_aec_agent.config import get_settings
from mini_aec_agent.exceptions import IFCModelError
from mini_aec_agent.ifc import IFCComplianceService, IFCModelService
from mini_aec_agent.ifc.service import (
    _extract_accessible_route_flag,
    _extract_explicit_clear_width,
)
from mini_aec_agent.ifc_tools import (
    check_ifc_element_compliance,
    get_ifc_element,
    get_ifc_summary,
    list_ifc_elements,
)
from mini_aec_agent.repository import JsonAECRepository

SAMPLE_IFC = Path(__file__).resolve().parents[1] / "examples" / "sample_office.ifc"


def test_ifc_summary_reports_project_and_counts() -> None:
    summary = IFCModelService(SAMPLE_IFC).summary()

    assert summary["schema"] == "IFC4"
    assert summary["project_name"] == "Sample Office"
    assert summary["class_counts"]["IfcDoor"] == 3


def test_ifc_door_query_preserves_guid_container_dimensions_and_psets() -> None:
    result = IFCModelService(SAMPLE_IFC).list_elements("IfcDoor")

    assert result["total"] == 3
    doors = {door["name"]: door for door in result["elements"]}
    assert doors["Door-01"]["global_id"]
    assert doors["Door-01"]["container"]["name"] == "Level 1"
    assert doors["Door-01"]["overall_width_mm"] == 780.0
    assert doors["Door-01"]["clear_width_mm"] == 780.0
    assert doors["Door-01"]["clear_width_source"] == "Pset_MiniAEC.ClearOpeningWidth"
    assert doors["Door-01"]["on_accessible_route"] is True
    assert (
        doors["Door-01"]["accessible_route_source"] == "Pset_MiniAEC.OnAccessibleRoute"
    )
    assert doors["Door-02"]["overall_width_mm"] == 1000.0
    assert doors["Door-02"]["property_sets"]["Pset_DoorCommon"]["IsExternal"]


def test_ifc_query_limit_is_reported() -> None:
    result = IFCModelService(SAMPLE_IFC).list_elements("IfcDoor", limit=1)

    assert result["returned"] == 1
    assert result["truncated"] is True


def test_clear_width_requires_an_ifc_length_measure() -> None:
    untyped_property = {
        "Pset_Demo": {"ClearOpeningWidth": {"value": 900.0, "value_type": "IfcReal"}}
    }

    assert _extract_explicit_clear_width(untyped_property, 0.001) is None


def test_accessible_route_requires_an_ifc_boolean() -> None:
    untyped_property = {
        "Pset_Demo": {"OnAccessibleRoute": {"value": "true", "value_type": "IfcLabel"}}
    }

    assert _extract_accessible_route_flag(untyped_property) is None


def test_ifc_element_lookup_by_guid() -> None:
    service = IFCModelService(SAMPLE_IFC)
    door = service.list_elements("IfcDoor", limit=1)["elements"][0]

    result = service.get_element(door["global_id"])

    assert result["name"] == "Door-01"


def test_ifc_element_lookup_reports_missing_guid() -> None:
    result = IFCModelService(SAMPLE_IFC).get_element("0000000000000000000000")

    assert "error" in result


def test_ifc_element_lookup_rejects_invalid_guid_shape() -> None:
    with pytest.raises(IFCModelError, match="22-character"):
        IFCModelService(SAMPLE_IFC).get_element("not-a-guid")


@pytest.mark.parametrize("limit", [0, 501])
def test_ifc_query_rejects_unbounded_limits(limit: int) -> None:
    with pytest.raises(IFCModelError, match="limit must be between"):
        IFCModelService(SAMPLE_IFC).list_elements("IfcDoor", limit=limit)


def test_ifc_query_rejects_invalid_class() -> None:
    with pytest.raises(IFCModelError, match="valid IFC class"):
        IFCModelService(SAMPLE_IFC).list_elements("Door; DROP")


def test_ifc_query_rejects_unknown_class() -> None:
    with pytest.raises(IFCModelError, match="Unknown or unsupported"):
        IFCModelService(SAMPLE_IFC).list_elements("IfcNotARealClass")


def test_ifc_service_rejects_missing_and_wrong_extension(tmp_path: Path) -> None:
    with pytest.raises(IFCModelError, match="extension"):
        IFCModelService(tmp_path / "model.txt")

    with pytest.raises(IFCModelError, match="not found"):
        IFCModelService(tmp_path / "missing.ifc")


def test_ifc_service_rejects_invalid_ifc_file(tmp_path: Path) -> None:
    invalid_file = tmp_path / "invalid.ifc"
    invalid_file.write_text("not an IFC file", encoding="utf-8")

    with pytest.raises(IFCModelError, match="Could not open"):
        IFCModelService(invalid_file)


def test_ifc_tools_use_configured_model() -> None:
    settings = replace(get_settings(), ifc_file=SAMPLE_IFC)
    summary = get_ifc_summary(settings)
    doors = list_ifc_elements("IfcDoor", 2, settings)
    global_id = doors["elements"][0]["global_id"]

    assert summary["class_counts"]["IfcDoor"] == 3
    assert get_ifc_element(global_id, settings)["name"] == "Door-01"


def test_agent_dispatches_ifc_tools() -> None:
    settings = replace(get_settings(), ifc_file=SAMPLE_IFC)

    summary = execute_tool("get_ifc_summary", {}, settings)
    doors = execute_tool(
        "list_ifc_elements", {"ifc_class": "IfcDoor", "limit": 1}, settings
    )

    assert summary["schema"] == "IFC4"
    assert doors["elements"][0]["global_id"]


def test_ifc_tools_require_configured_model() -> None:
    settings = replace(get_settings(), ifc_file=None)

    with pytest.raises(ValueError, match="No IFC model"):
        get_ifc_summary(settings)


def test_agent_validates_ifc_tool_inputs() -> None:
    assert "error" in execute_tool("list_ifc_elements", {})
    assert "error" in execute_tool(
        "list_ifc_elements", {"ifc_class": "IfcDoor", "limit": "one"}
    )
    assert "error" in execute_tool("get_ifc_element", {"global_id": ""})
    assert "error" in execute_tool("check_ifc_element_compliance", {"global_id": ""})
    assert "error" in execute_tool(
        "get_ifc_element", {"global_id": "!!!!!!!!!!!!!!!!!!!!!!"}
    )


def test_ifc_door_compliance_uses_real_dimensions_and_provenance() -> None:
    model_service = IFCModelService(SAMPLE_IFC)
    settings = replace(get_settings(), regulations_file=get_settings().ifc_rules_file)
    repository = JsonAECRepository(settings)
    compliance_service = IFCComplianceService(model_service, repository)
    doors = model_service.list_elements("IfcDoor")["elements"]
    door_ids = {door["name"]: door["global_id"] for door in doors}

    failing = compliance_service.check_element(door_ids["Door-01"])
    passing = compliance_service.check_element(door_ids["Door-02"])

    assert failing["overall_status"] == "FAIL"
    assert failing["checks"][0]["actual_value"] == 780.0
    assert failing["checks"][0]["required_value"] == 800
    assert failing["checks"][0]["rule_id"] == "HK-BFA-DOOR-WIDTH-038"
    assert failing["checks"][0]["source"]["pdf_page"] == 66
    assert failing["checks"][0]["source"]["clause_id"] == "38"
    assert failing["rule_catalog"]["version"] == "2025.1.0"
    assert failing["evidence"]["source_file"] == "sample_office.ifc"
    assert failing["evidence"]["global_id"] == door_ids["Door-01"]
    assert failing["evidence"]["source_fields"] == {
        "width_mm": "Pset_MiniAEC.ClearOpeningWidth",
        "applicability": "Pset_MiniAEC.OnAccessibleRoute",
    }
    assert passing["overall_status"] == "PASS"


def test_ifc_compliance_does_not_treat_overall_width_as_clear_width(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = IFCModelService(SAMPLE_IFC)
    record = service.list_elements("IfcDoor", limit=1)["elements"][0]
    record.pop("clear_width_mm")
    record.pop("clear_width_source")
    monkeypatch.setattr(service, "get_element", lambda global_id: record)
    settings = replace(get_settings(), regulations_file=get_settings().ifc_rules_file)
    repository = JsonAECRepository(settings)

    result = IFCComplianceService(service, repository).check_element(
        str(record["global_id"])
    )

    assert result["overall_status"] == "UNKNOWN"
    assert result["checks"][0]["status"] == "UNKNOWN"
    assert result["evidence"]["source_fields"] == {
        "applicability": "Pset_MiniAEC.OnAccessibleRoute"
    }


@pytest.mark.parametrize(
    ("route_value", "expected_check_status"),
    [(None, "UNKNOWN"), (False, "NOT_APPLICABLE")],
)
def test_ifc_compliance_requires_explicit_accessible_route_applicability(
    route_value: bool | None,
    expected_check_status: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = IFCModelService(SAMPLE_IFC)
    record = service.list_elements("IfcDoor", limit=1)["elements"][0]
    if route_value is None:
        record.pop("on_accessible_route")
        record.pop("accessible_route_source")
    else:
        record["on_accessible_route"] = route_value
    monkeypatch.setattr(service, "get_element", lambda global_id: record)
    settings = replace(get_settings(), regulations_file=get_settings().ifc_rules_file)

    result = IFCComplianceService(service, JsonAECRepository(settings)).check_element(
        str(record["global_id"])
    )

    assert result["overall_status"] == "UNKNOWN"
    assert result["checks"][0]["status"] == expected_check_status


def test_ifc_compliance_tool_runs_from_agent_dispatch() -> None:
    settings = replace(get_settings(), ifc_file=SAMPLE_IFC)
    door = list_ifc_elements("IfcDoor", 1, settings)["elements"][0]

    result = execute_tool(
        "check_ifc_element_compliance", {"global_id": door["global_id"]}, settings
    )

    assert result["overall_status"] == "FAIL"
    assert result["evidence"]["source_type"] == "IFC"


def test_ifc_compliance_reports_unsupported_entity() -> None:
    service = IFCModelService(SAMPLE_IFC)
    settings = replace(get_settings(), regulations_file=get_settings().ifc_rules_file)
    repository = JsonAECRepository(settings)
    project_id = service.summary()
    project = next(iter(service.model.by_type("IfcProject")))

    result = IFCComplianceService(service, repository).check_element(project.GlobalId)

    assert project_id["project_name"] == "Sample Office"
    assert result["overall_status"] == "UNKNOWN"
    assert "No compliance adapter" in result["reason"]
    assert result["evidence"]["source_fields"] == {}


def test_ifc_compliance_reports_missing_guid() -> None:
    settings = replace(get_settings(), ifc_file=SAMPLE_IFC)

    result = check_ifc_element_compliance("0000000000000000000000", settings)

    assert "error" in result
