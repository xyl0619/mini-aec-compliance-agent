"""Stable tool functions exposed to the LLM and external callers."""

from __future__ import annotations

from mini_aec_agent.compliance import check_item_compliance
from mini_aec_agent.config import Settings
from mini_aec_agent.repository import JsonAECRepository, JsonObject


def load_building(settings: Settings | None = None) -> JsonObject:
    return JsonAECRepository(settings).load_building()


def load_regulations(settings: Settings | None = None) -> JsonObject:
    return JsonAECRepository(settings).load_regulations()


def get_item(item_id: str, settings: Settings | None = None) -> JsonObject:
    item = JsonAECRepository(settings).find_item(item_id)
    if item is None:
        return {"error": f"Item '{item_id}' was not found."}
    return item


def list_items(
    item_type: str = "all", settings: Settings | None = None
) -> list[JsonObject]:
    return JsonAECRepository(settings).list_items(item_type)


__all__ = [
    "check_item_compliance",
    "get_item",
    "list_items",
    "load_building",
    "load_regulations",
]
