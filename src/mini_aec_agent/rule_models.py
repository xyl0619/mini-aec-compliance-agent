"""Typed, versioned schemas for deterministic compliance rules."""

from __future__ import annotations

import math
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

RuleOperator = Literal[">=", "<=", ">", "<", "=="]
CatalogStatus = Literal["demonstration", "prototype", "validated"]


class RuleSource(BaseModel):
    """Trace one machine-readable rule back to its human source."""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    document_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=500)
    source_url: str | None = Field(default=None, max_length=2000)
    pdf_page: int | None = Field(default=None, ge=1)
    clause_id: str | None = Field(default=None, max_length=128)
    section: str | None = Field(default=None, max_length=500)
    verified: bool = False
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("source_url must be an absolute HTTP(S) URL")
        return value


class ComplianceRule(BaseModel):
    """One deterministic comparison with optional legal provenance."""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    rule_id: str = Field(min_length=1, max_length=128)
    version: str = Field(default="1.0", min_length=1, max_length=64)
    applies_to: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    field: str = Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_]*$")
    operator: RuleOperator
    threshold: int | float | str | bool
    unit: str = Field(max_length=64)
    description: str = Field(min_length=1, max_length=1000)
    applicability_field: str | None = Field(
        default=None, max_length=128, pattern=r"^[a-z][a-z0-9_]*$"
    )
    applicability_value: int | float | str | bool | None = None
    source: RuleSource | None = None

    @model_validator(mode="after")
    def validate_comparison(self) -> Self:
        if isinstance(self.threshold, float) and not math.isfinite(self.threshold):
            raise ValueError("threshold must be finite")
        if self.operator != "==" and isinstance(self.threshold, (str, bool)):
            raise ValueError("ordered comparisons require a numeric threshold")
        if (self.applicability_field is None) != (self.applicability_value is None):
            raise ValueError(
                "applicability_field and applicability_value must be provided together"
            )
        if isinstance(self.applicability_value, float) and not math.isfinite(
            self.applicability_value
        ):
            raise ValueError("applicability_value must be finite")
        return self


class RuleCatalog(BaseModel):
    """Versioned collection of deterministic rules."""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    schema_version: Literal[1] = 1
    catalog_id: str = Field(default="legacy-demo-catalog", min_length=1, max_length=128)
    title: str = Field(
        default="Legacy demonstration rules", min_length=1, max_length=500
    )
    version: str = Field(default="1.0.0", min_length=1, max_length=64)
    jurisdiction: str = Field(
        default="Demonstration only", min_length=1, max_length=200
    )
    status: CatalogStatus = "demonstration"
    note: str | None = Field(default=None, max_length=2000)
    rules: list[ComplianceRule] = Field(max_length=10_000)

    @model_validator(mode="after")
    def validate_catalog(self) -> Self:
        normalized_ids = [rule.rule_id.casefold() for rule in self.rules]
        if len(normalized_ids) != len(set(normalized_ids)):
            raise ValueError("rule_id values must be unique within a catalog")
        if self.status in {"prototype", "validated"} and any(
            rule.source is None for rule in self.rules
        ):
            raise ValueError("prototype and validated rules require source provenance")
        if self.status == "validated" and any(
            rule.source is None or not rule.source.verified for rule in self.rules
        ):
            raise ValueError("validated rules require verified source provenance")
        return self
