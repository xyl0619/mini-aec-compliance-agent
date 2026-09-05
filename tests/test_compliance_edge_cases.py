from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from mini_aec_agent.compliance import ComplianceEngine, compare_values
from mini_aec_agent.config import get_settings
from mini_aec_agent.exceptions import (
    DataSourceError,
    UnsupportedRuleOperatorError,
)
from mini_aec_agent.repository import JsonAECRepository
from mini_aec_agent.tools import load_building, load_regulations


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_missing_rule_field_produces_unknown(tmp_path: Path) -> None:
    building_file = tmp_path / "building.json"
    regulations_file = tmp_path / "regulations.json"
    _write_json(
        building_file,
        {
            "components": [{"id": "Door-X", "type": "door"}],
            "spaces": [],
        },
    )
    _write_json(
        regulations_file,
        {
            "rules": [
                {
                    "rule_id": "WIDTH",
                    "applies_to": "door",
                    "field": "width_mm",
                    "operator": ">=",
                    "threshold": 900,
                    "unit": "mm",
                    "description": "Minimum width",
                }
            ]
        },
    )
    settings = replace(
        get_settings(),
        building_file=building_file,
        regulations_file=regulations_file,
    )

    result = ComplianceEngine(JsonAECRepository(settings)).check_item("Door-X")

    assert result["overall_status"] == "UNKNOWN"
    assert result["checks"][0]["status"] == "UNKNOWN"


def test_item_without_applicable_rules_is_unknown(tmp_path: Path) -> None:
    building_file = tmp_path / "building.json"
    regulations_file = tmp_path / "regulations.json"
    _write_json(
        building_file,
        {
            "components": [{"id": "Wall-X", "type": "wall"}],
            "spaces": [],
        },
    )
    _write_json(regulations_file, {"rules": []})
    settings = replace(
        get_settings(),
        building_file=building_file,
        regulations_file=regulations_file,
    )

    result = ComplianceEngine(JsonAECRepository(settings)).check_item("Wall-X")

    assert result["overall_status"] == "UNKNOWN"
    assert result["checks"] == []


def test_repository_rejects_invalid_building_shape(tmp_path: Path) -> None:
    building_file = tmp_path / "building.json"
    _write_json(building_file, {"components": []})
    settings = replace(get_settings(), building_file=building_file)

    with pytest.raises(DataSourceError):
        JsonAECRepository(settings).load_building()


def test_repository_rejects_duplicate_or_malformed_building_items(
    tmp_path: Path,
) -> None:
    building_file = tmp_path / "building.json"
    _write_json(
        building_file,
        {
            "components": [{"id": "Door-X", "type": "door"}],
            "spaces": [{"id": "door-x", "type": "office"}],
        },
    )
    settings = replace(get_settings(), building_file=building_file)

    with pytest.raises(DataSourceError, match="Invalid building data"):
        JsonAECRepository(settings).load_building()

    _write_json(building_file, {"project_name": " ", "components": [], "spaces": []})
    with pytest.raises(DataSourceError, match="Invalid building data"):
        JsonAECRepository(settings).load_building()

    _write_json(building_file, {"components": ["not-an-object"], "spaces": []})
    with pytest.raises(DataSourceError, match="Invalid building data"):
        JsonAECRepository(settings).load_building()


def test_non_finite_json_and_incompatible_rule_values_are_safe(
    tmp_path: Path,
) -> None:
    building_file = tmp_path / "building.json"
    building_file.write_text(
        '{"components":[{"id":"Door-X","type":"door","width_mm":NaN}],"spaces":[]}',
        encoding="utf-8",
    )
    settings = replace(get_settings(), building_file=building_file)
    with pytest.raises(DataSourceError, match="Invalid JSON"):
        JsonAECRepository(settings).load_building()

    building_file.write_text(
        '{"components":[],"components":[],"spaces":[]}', encoding="utf-8"
    )
    with pytest.raises(DataSourceError, match="Invalid JSON"):
        JsonAECRepository(settings).load_building()

    _write_json(
        building_file,
        {
            "components": [{"id": "Door-X", "type": "door", "width_mm": "wide"}],
            "spaces": [],
        },
    )
    result = ComplianceEngine(JsonAECRepository(settings)).check_item("Door-X")
    assert result["overall_status"] == "UNKNOWN"
    assert "incompatible" in result["checks"][0]["reason"]


def test_compare_values_rejects_unknown_operator() -> None:
    with pytest.raises(UnsupportedRuleOperatorError):
        compare_values(1, "!=", 2)


@pytest.mark.parametrize("actual", [float("nan"), float("inf"), True, "1000"])
def test_ordered_comparison_rejects_non_numeric_actual(actual: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        compare_values(actual, ">=", 900)


def test_equality_rejects_incompatible_actual_type() -> None:
    with pytest.raises(TypeError):
        compare_values("true", "==", True)


def test_repository_rejects_invalid_json(tmp_path: Path) -> None:
    building_file = tmp_path / "building.json"
    building_file.write_text("not-json", encoding="utf-8")
    settings = replace(get_settings(), building_file=building_file)

    with pytest.raises(DataSourceError, match="Invalid JSON"):
        JsonAECRepository(settings).load_building()


def test_repository_reports_missing_file(tmp_path: Path) -> None:
    settings = replace(get_settings(), building_file=tmp_path / "missing.json")

    with pytest.raises(DataSourceError, match="Could not read"):
        JsonAECRepository(settings).load_building()


def test_repository_rejects_invalid_regulations_shape(tmp_path: Path) -> None:
    regulations_file = tmp_path / "regulations.json"
    _write_json(regulations_file, {"note": "missing rules"})
    settings = replace(get_settings(), regulations_file=regulations_file)

    with pytest.raises(DataSourceError, match="Invalid rule catalog"):
        JsonAECRepository(settings).load_regulations()


def test_repository_rejects_invalid_rule_operator(tmp_path: Path) -> None:
    regulations_file = tmp_path / "regulations.json"
    _write_json(
        regulations_file,
        {
            "rules": [
                {
                    "rule_id": "INVALID",
                    "applies_to": "door",
                    "field": "width_mm",
                    "operator": "!=",
                    "threshold": 900,
                    "unit": "mm",
                    "description": "Invalid operator",
                }
            ]
        },
    )
    settings = replace(get_settings(), regulations_file=regulations_file)

    with pytest.raises(DataSourceError, match="Invalid rule catalog"):
        JsonAECRepository(settings).load_regulations()


def test_repository_rejects_incomplete_rule_applicability(tmp_path: Path) -> None:
    regulations_file = tmp_path / "regulations.json"
    _write_json(
        regulations_file,
        {
            "rules": [
                {
                    "rule_id": "CONDITIONAL-WIDTH",
                    "applies_to": "door",
                    "field": "width_mm",
                    "operator": ">=",
                    "threshold": 900,
                    "unit": "mm",
                    "description": "Conditional minimum width",
                    "applicability_field": "on_accessible_route",
                }
            ]
        },
    )
    settings = replace(get_settings(), regulations_file=regulations_file)

    with pytest.raises(DataSourceError, match="Invalid rule catalog"):
        JsonAECRepository(settings).load_regulations()


def test_repository_rejects_duplicate_and_unprovenanced_prototype_rules(
    tmp_path: Path,
) -> None:
    regulations_file = tmp_path / "regulations.json"
    rule = {
        "rule_id": "WIDTH",
        "applies_to": "door",
        "field": "width_mm",
        "operator": ">=",
        "threshold": 900,
        "unit": "mm",
        "description": "Minimum width",
    }
    _write_json(regulations_file, {"rules": [rule, dict(rule)]})
    settings = replace(get_settings(), regulations_file=regulations_file)
    with pytest.raises(DataSourceError, match="Invalid rule catalog"):
        JsonAECRepository(settings).load_regulations()

    _write_json(
        regulations_file,
        {"status": "prototype", "rules": [rule]},
    )
    with pytest.raises(DataSourceError, match="Invalid rule catalog"):
        JsonAECRepository(settings).load_regulations()


def test_public_load_helpers_return_demo_data() -> None:
    assert load_building()["project_name"] == "Demo Office Building"
    catalog = load_regulations()
    assert len(catalog["rules"]) == 3
    assert catalog["catalog_id"] == "mini-aec-fictional-demo"
    assert catalog["status"] == "demonstration"
