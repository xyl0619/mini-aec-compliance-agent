"""Deterministic compliance evaluation used as the source of truth."""

from __future__ import annotations

import math
from typing import Any

from mini_aec_agent.config import Settings
from mini_aec_agent.exceptions import UnsupportedRuleOperatorError
from mini_aec_agent.repository import JsonAECRepository, JsonObject


def compare_values(actual: Any, operator: str, threshold: Any) -> bool:
    """Evaluate one supported deterministic rule comparison."""

    if isinstance(actual, float) and not math.isfinite(actual):
        raise ValueError("Actual value must be finite.")
    if isinstance(threshold, float) and not math.isfinite(threshold):
        raise ValueError("Threshold must be finite.")
    if operator in {">=", "<=", ">", "<"} and (
        isinstance(actual, bool) or not isinstance(actual, (int, float))
    ):
        raise TypeError("Ordered comparisons require a numeric actual value.")
    if operator == "==":
        if isinstance(threshold, bool) and not isinstance(actual, bool):
            raise TypeError("Boolean equality requires a boolean actual value.")
        if isinstance(threshold, str) and not isinstance(actual, str):
            raise TypeError("Text equality requires a text actual value.")
        if (
            isinstance(threshold, (int, float))
            and not isinstance(threshold, bool)
            and (isinstance(actual, bool) or not isinstance(actual, (int, float)))
        ):
            raise TypeError("Numeric equality requires a numeric actual value.")

    comparisons = {
        ">=": lambda: actual >= threshold,
        "<=": lambda: actual <= threshold,
        ">": lambda: actual > threshold,
        "<": lambda: actual < threshold,
        "==": lambda: actual == threshold,
    }

    try:
        return comparisons[operator]()
    except KeyError as error:
        raise UnsupportedRuleOperatorError(
            f"Unsupported rule operator: {operator}"
        ) from error


class ComplianceEngine:
    """Apply every relevant rule to one building item."""

    def __init__(self, repository: JsonAECRepository | None = None) -> None:
        self.repository = repository or JsonAECRepository()

    def get_applicable_rules(self, item: JsonObject) -> list[JsonObject]:
        rules = self.repository.load_regulations()["rules"]
        return self._filter_applicable_rules(item, rules)

    @staticmethod
    def _filter_applicable_rules(
        item: JsonObject, rules: list[JsonObject]
    ) -> list[JsonObject]:
        item_type = item.get("type")

        return [
            rule
            for rule in rules
            if rule.get("applies_to") == item_type
            or (
                rule.get("applies_to") == "space"
                and item_type in {"office", "meeting_room"}
            )
        ]

    def check_item(self, item_id: str) -> JsonObject:
        item = self.repository.find_item(item_id)
        if item is None:
            return {"error": f"Item '{item_id}' was not found."}

        return self.evaluate_item(item)

    def evaluate_item(self, item: JsonObject) -> JsonObject:
        """Evaluate an already-normalized item against the rule catalog."""

        catalog = self.repository.load_regulations()
        applicable_rules = self._filter_applicable_rules(item, catalog["rules"])
        checks: list[JsonObject] = []
        for rule in applicable_rules:
            applicability_field = rule.get("applicability_field")
            if isinstance(applicability_field, str):
                if applicability_field not in item:
                    checks.append(
                        {
                            "rule_id": rule["rule_id"],
                            "rule_version": rule["version"],
                            "description": rule["description"],
                            "status": "UNKNOWN",
                            "reason": (
                                "Required applicability field "
                                f"'{applicability_field}' is missing."
                            ),
                            "source": rule.get("source"),
                        }
                    )
                    continue
                try:
                    is_applicable = compare_values(
                        item[applicability_field],
                        "==",
                        rule.get("applicability_value"),
                    )
                except (TypeError, ValueError):
                    checks.append(
                        {
                            "rule_id": rule["rule_id"],
                            "rule_version": rule["version"],
                            "description": rule["description"],
                            "status": "UNKNOWN",
                            "reason": "Applicability evidence has an incompatible type.",
                            "source": rule.get("source"),
                        }
                    )
                    continue
                if not is_applicable:
                    checks.append(
                        {
                            "rule_id": rule["rule_id"],
                            "rule_version": rule["version"],
                            "description": rule["description"],
                            "status": "NOT_APPLICABLE",
                            "actual_value": item[applicability_field],
                            "applicability_field": applicability_field,
                            "required_value": rule.get("applicability_value"),
                            "source": rule.get("source"),
                        }
                    )
                    continue

            field = rule["field"]

            if field not in item:
                checks.append(
                    {
                        "rule_id": rule["rule_id"],
                        "rule_version": rule["version"],
                        "status": "UNKNOWN",
                        "reason": f"Required field '{field}' is missing.",
                        "source": rule.get("source"),
                    }
                )
                continue

            actual_value = item[field]
            try:
                passed = compare_values(
                    actual_value, rule["operator"], rule["threshold"]
                )
            except (TypeError, ValueError):
                checks.append(
                    {
                        "rule_id": rule["rule_id"],
                        "rule_version": rule["version"],
                        "description": rule["description"],
                        "status": "UNKNOWN",
                        "actual_value": actual_value,
                        "reason": "Actual value is incompatible with the rule threshold.",
                        "source": rule.get("source"),
                    }
                )
                continue
            checks.append(
                {
                    "rule_id": rule["rule_id"],
                    "rule_version": rule["version"],
                    "description": rule["description"],
                    "status": "PASS" if passed else "FAIL",
                    "actual_value": actual_value,
                    "operator": rule["operator"],
                    "required_value": rule["threshold"],
                    "unit": rule["unit"],
                    "source": rule.get("source"),
                }
            )

        if any(check["status"] == "FAIL" for check in checks):
            overall_status = "FAIL"
        elif not checks or any(check["status"] == "UNKNOWN" for check in checks):
            overall_status = "UNKNOWN"
        elif any(check["status"] == "PASS" for check in checks):
            overall_status = "PASS"
        else:
            overall_status = "UNKNOWN"

        return {
            "item": item,
            "overall_status": overall_status,
            "checks": checks,
            "rule_catalog": {
                "catalog_id": catalog["catalog_id"],
                "version": catalog["version"],
                "jurisdiction": catalog["jurisdiction"],
                "status": catalog["status"],
            },
        }


def get_applicable_rules(
    item: JsonObject, settings: Settings | None = None
) -> list[JsonObject]:
    """Compatibility function for callers that do not manage an engine."""

    return ComplianceEngine(JsonAECRepository(settings)).get_applicable_rules(item)


def check_item_compliance(item_id: str, settings: Settings | None = None) -> JsonObject:
    """Check one item using the configured deterministic rule catalog."""

    return ComplianceEngine(JsonAECRepository(settings)).check_item(item_id)
