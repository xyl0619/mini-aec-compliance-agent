"""Read-only IFC model access built on IfcOpenShell."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.unit

from mini_aec_agent.exceptions import IFCModelError

JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
IfcRecord = dict[str, JsonValue]
IFC_GUID_PATTERN = re.compile(r"^[0-9A-Za-z_$]{22}$")
MAX_IFC_FILE_BYTES = 512 * 1024 * 1024
MAX_JSON_COLLECTION_ITEMS = 1000
MAX_JSON_DEPTH = 8
MAX_JSON_TEXT_LENGTH = 10_000
CLEAR_WIDTH_PROPERTY_NAMES = ("ClearOpeningWidth", "ClearWidth")
ACCESSIBLE_ROUTE_PROPERTY_NAMES = ("OnAccessibleRoute", "IsOnAccessibleRoute")
IFC_LENGTH_VALUE_TYPES = {
    "IfcLengthMeasure",
    "IfcNonNegativeLengthMeasure",
    "IfcPositiveLengthMeasure",
}


def is_valid_ifc_guid(value: str) -> bool:
    """Return whether a value has the standard 22-character IFC GUID shape."""

    return IFC_GUID_PATTERN.fullmatch(value) is not None


def _json_safe(value: Any, depth: int = 0) -> JsonValue:
    """Convert IFC utility output into a JSON-serializable value."""

    if depth >= MAX_JSON_DEPTH:
        return "<maximum depth reached>"
    if isinstance(value, str):
        return value[:MAX_JSON_TEXT_LENGTH]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if value is None or isinstance(value, (int, bool)):
        return value
    if isinstance(value, dict):
        result: dict[str, JsonValue] = {}
        for index, (key, nested) in enumerate(value.items()):
            if index >= MAX_JSON_COLLECTION_ITEMS:
                result["_truncated"] = True
                break
            if key != "id":
                result[str(key)[:MAX_JSON_TEXT_LENGTH]] = _json_safe(nested, depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        list_result = [
            _json_safe(item, depth + 1) for item in value[:MAX_JSON_COLLECTION_ITEMS]
        ]
        if len(value) > MAX_JSON_COLLECTION_ITEMS:
            list_result.append("<truncated>")
        return list_result
    if hasattr(value, "is_a"):
        return str(value)
    return str(value)[:MAX_JSON_TEXT_LENGTH]


def _extract_explicit_clear_width(
    property_sets: Any, length_scale_to_meters: float
) -> tuple[float, str] | None:
    """Return an explicitly named clear-opening width and its IFC property path."""

    if not isinstance(property_sets, dict):
        return None
    for property_name in CLEAR_WIDTH_PROPERTY_NAMES:
        for pset_name in sorted(property_sets, key=str):
            properties = property_sets[pset_name]
            if not isinstance(properties, dict):
                continue
            matched_key = next(
                (
                    key
                    for key in properties
                    if str(key).casefold() == property_name.casefold()
                ),
                None,
            )
            if matched_key is None:
                continue
            property_record = properties[matched_key]
            if (
                not isinstance(property_record, dict)
                or property_record.get("value_type") not in IFC_LENGTH_VALUE_TYPES
            ):
                continue
            raw_value = property_record.get("value")
            if raw_value is None:
                continue
            if isinstance(raw_value, bool):
                continue
            try:
                value_mm = float(raw_value) * length_scale_to_meters * 1000
            except (TypeError, ValueError, OverflowError):
                continue
            if math.isfinite(value_mm) and value_mm >= 0:
                return round(value_mm, 3), f"{pset_name}.{matched_key}"
    return None


def _extract_accessible_route_flag(property_sets: Any) -> tuple[bool, str] | None:
    """Return an explicitly typed accessible-route flag and its property path."""

    if not isinstance(property_sets, dict):
        return None
    for property_name in ACCESSIBLE_ROUTE_PROPERTY_NAMES:
        for pset_name in sorted(property_sets, key=str):
            properties = property_sets[pset_name]
            if not isinstance(properties, dict):
                continue
            matched_key = next(
                (
                    key
                    for key in properties
                    if str(key).casefold() == property_name.casefold()
                ),
                None,
            )
            if matched_key is None:
                continue
            property_record = properties[matched_key]
            if (
                not isinstance(property_record, dict)
                or property_record.get("value_type") != "IfcBoolean"
                or not isinstance(property_record.get("value"), bool)
            ):
                continue
            return bool(property_record["value"]), f"{pset_name}.{matched_key}"
    return None


class IFCModelService:
    """Load one IFC file and expose bounded, JSON-safe model queries."""

    MAX_QUERY_LIMIT = 500

    def __init__(self, file_path: str | Path) -> None:
        self.file_path = Path(file_path).expanduser().resolve()
        if self.file_path.suffix.casefold() != ".ifc":
            raise IFCModelError("IFC source must use the .ifc extension.")
        if not self.file_path.is_file():
            raise IFCModelError(f"IFC file was not found: {self.file_path}")

        try:
            if self.file_path.stat().st_size > MAX_IFC_FILE_BYTES:
                raise IFCModelError(
                    f"IFC file exceeds the {MAX_IFC_FILE_BYTES}-byte safety limit."
                )
            with self.file_path.open("rb") as file:
                header = file.read(65_536)
        except IFCModelError:
            raise
        except OSError as error:
            raise IFCModelError(f"Could not read IFC file: {self.file_path}") from error
        if b"ISO-10303-21;" not in header or b"FILE_SCHEMA" not in header:
            raise IFCModelError(f"Could not open IFC file: {self.file_path}")

        try:
            self.model = ifcopenshell.open(str(self.file_path))
        except Exception as error:
            raise IFCModelError(f"Could not open IFC file: {self.file_path}") from error

        try:
            self.length_scale_to_meters = ifcopenshell.util.unit.calculate_unit_scale(
                self.model
            )
        except Exception:
            self.length_scale_to_meters = 1.0

    def summary(self) -> IfcRecord:
        project = next(iter(self.model.by_type("IfcProject")), None)
        classes = [
            "IfcSite",
            "IfcBuilding",
            "IfcBuildingStorey",
            "IfcSpace",
            "IfcWall",
            "IfcDoor",
            "IfcWindow",
            "IfcStair",
        ]
        counts = {
            ifc_class: len(self.model.by_type(ifc_class)) for ifc_class in classes
        }
        return {
            "source_file": self.file_path.name,
            "schema": self.model.schema,
            "project_name": getattr(project, "Name", None) if project else None,
            "entity_count": sum(1 for _ in self.model),
            "class_counts": counts,
        }

    def list_elements(self, ifc_class: str, limit: int = 100) -> IfcRecord:
        if (
            len(ifc_class) > 64
            or not ifc_class.startswith("Ifc")
            or not ifc_class.isalnum()
        ):
            raise IFCModelError("ifc_class must be a valid IFC class name.")
        if not 1 <= limit <= self.MAX_QUERY_LIMIT:
            raise IFCModelError(f"limit must be between 1 and {self.MAX_QUERY_LIMIT}.")

        try:
            elements = list(self.model.by_type(ifc_class))
        except RuntimeError as error:
            raise IFCModelError(
                f"Unknown or unsupported IFC class: {ifc_class}"
            ) from error

        records: list[JsonValue] = [
            self._element_record(element) for element in elements[:limit]
        ]
        return {
            "source_file": self.file_path.name,
            "ifc_class": ifc_class,
            "total": len(elements),
            "returned": len(records),
            "truncated": len(records) < len(elements),
            "elements": records,
        }

    def get_element(self, global_id: str) -> IfcRecord:
        if not is_valid_ifc_guid(global_id):
            raise IFCModelError("global_id must be a valid 22-character IFC GUID.")

        try:
            element = self.model.by_guid(global_id)
        except RuntimeError:
            element = None

        if element is None:
            return {"error": f"IFC element '{global_id}' was not found."}

        return self._element_record(element)

    def _element_record(self, element: Any) -> IfcRecord:
        try:
            container = ifcopenshell.util.element.get_container(element)
        except Exception:
            container = None

        try:
            property_sets = ifcopenshell.util.element.get_psets(
                element, psets_only=True
            )
            verbose_property_sets = ifcopenshell.util.element.get_psets(
                element, psets_only=True, verbose=True
            )
            quantities = ifcopenshell.util.element.get_psets(element, qtos_only=True)
        except Exception as error:
            raise IFCModelError("Could not extract IFC element properties.") from error

        record: IfcRecord = {
            "global_id": getattr(element, "GlobalId", None),
            "ifc_class": element.is_a(),
            "name": getattr(element, "Name", None),
            "description": getattr(element, "Description", None),
            "container": (
                {
                    "global_id": getattr(container, "GlobalId", None),
                    "ifc_class": container.is_a(),
                    "name": getattr(container, "Name", None),
                }
                if container
                else None
            ),
            "property_sets": _json_safe(property_sets),
            "quantities": _json_safe(quantities),
        }

        clear_width = _extract_explicit_clear_width(
            verbose_property_sets, self.length_scale_to_meters
        )
        if clear_width is not None:
            record["clear_width_mm"] = clear_width[0]
            record["clear_width_source"] = clear_width[1]
        accessible_route = _extract_accessible_route_flag(verbose_property_sets)
        if accessible_route is not None:
            record["on_accessible_route"] = accessible_route[0]
            record["accessible_route_source"] = accessible_route[1]

        overall_width = getattr(element, "OverallWidth", None)
        overall_height = getattr(element, "OverallHeight", None)
        if overall_width is not None:
            try:
                width_mm = float(overall_width) * self.length_scale_to_meters * 1000
            except (TypeError, ValueError, OverflowError):
                width_mm = math.nan
            if math.isfinite(width_mm):
                record["overall_width_mm"] = round(width_mm, 3)
        if overall_height is not None:
            try:
                height_mm = float(overall_height) * self.length_scale_to_meters * 1000
            except (TypeError, ValueError, OverflowError):
                height_mm = math.nan
            if math.isfinite(height_mm):
                record["overall_height_mm"] = round(height_mm, 3)

        return record
