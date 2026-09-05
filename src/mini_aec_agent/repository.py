"""Data access for the demonstration building and rule catalog."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from mini_aec_agent.building_models import BuildingData, dump_building
from mini_aec_agent.config import Settings, get_settings
from mini_aec_agent.exceptions import DataSourceError
from mini_aec_agent.json_utils import reject_duplicate_keys, reject_non_finite_number
from mini_aec_agent.rule_models import RuleCatalog

JsonObject = dict[str, Any]
MAX_DATA_FILE_BYTES = 16 * 1024 * 1024


class JsonAECRepository:
    """Read AEC objects and rules from configurable JSON files."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @staticmethod
    def _load_json(file_path: Path) -> JsonObject:
        try:
            if file_path.stat().st_size > MAX_DATA_FILE_BYTES:
                raise DataSourceError(
                    f"Data file exceeds {MAX_DATA_FILE_BYTES} bytes: {file_path}"
                )
            with file_path.open("r", encoding="utf-8") as file:
                payload = json.load(
                    file,
                    parse_constant=reject_non_finite_number,
                    object_pairs_hook=reject_duplicate_keys,
                )
        except DataSourceError:
            raise
        except OSError as error:
            raise DataSourceError(f"Could not read data file: {file_path}") from error
        except (json.JSONDecodeError, RecursionError, ValueError) as error:
            raise DataSourceError(f"Invalid JSON data file: {file_path}") from error

        if not isinstance(payload, dict):
            raise DataSourceError(f"Expected a JSON object in: {file_path}")

        return payload

    def load_building(self) -> JsonObject:
        building = self._load_json(self.settings.building_file)
        try:
            validated = BuildingData.model_validate(building)
        except ValidationError as error:
            raise DataSourceError(f"Invalid building data: {error}") from error
        return dump_building(validated)

    def load_regulations(self) -> JsonObject:
        regulations = self._load_json(self.settings.regulations_file)
        try:
            catalog = RuleCatalog.model_validate(regulations)
        except ValidationError as error:
            raise DataSourceError(f"Invalid rule catalog: {error}") from error
        return catalog.model_dump(mode="json")

    def list_items(self, item_type: str = "all") -> list[JsonObject]:
        building = self.load_building()
        items = [*building["components"], *building["spaces"]]

        if item_type == "all":
            return items

        return [item for item in items if item.get("type") == item_type]

    def find_item(self, item_id: str) -> JsonObject | None:
        normalized_id = item_id.casefold()
        return next(
            (
                item
                for item in self.list_items()
                if str(item.get("id", "")).casefold() == normalized_id
            ),
            None,
        )
