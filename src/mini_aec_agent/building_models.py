"""Validated schemas for JSON building inputs."""

from __future__ import annotations

from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class BuildingItem(BaseModel):
    """One extensible building record with stable identity fields."""

    model_config = ConfigDict(extra="allow", strict=True, str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=128)
    type: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    location: str | None = Field(default=None, max_length=500)

    @field_validator("id", "location")
    @classmethod
    def reject_blank_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("text fields cannot be blank")
        return value.strip() if value is not None else None


class BuildingData(BaseModel):
    """Top-level building data with bounded collections and unique item IDs."""

    model_config = ConfigDict(extra="allow", strict=True, str_strip_whitespace=True)

    project_name: str | None = Field(default=None, max_length=500)
    components: list[BuildingItem] = Field(max_length=10_000)
    spaces: list[BuildingItem] = Field(max_length=10_000)

    @field_validator("project_name")
    @classmethod
    def reject_blank_project_name(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("project_name cannot be blank")
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def ensure_unique_ids(self) -> Self:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for item in [*self.components, *self.spaces]:
            normalized = item.id.casefold()
            if normalized in seen:
                duplicates.add(item.id)
            seen.add(normalized)
        if duplicates:
            duplicate_list = ", ".join(sorted(duplicates))
            raise ValueError(f"building item IDs must be unique: {duplicate_list}")
        return self


def dump_building(data: BuildingData) -> dict[str, Any]:
    """Return a JSON-compatible mapping while retaining permitted extra fields."""

    return data.model_dump(mode="json")
