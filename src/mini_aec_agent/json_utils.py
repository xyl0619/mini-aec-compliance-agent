"""Strict JSON decoding helpers shared by trusted-data boundaries."""

from __future__ import annotations

from typing import Any


def reject_non_finite_number(value: str) -> None:
    """Reject JavaScript-style NaN and infinity extensions."""

    raise ValueError(f"Non-finite JSON number is not allowed: {value}")


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Build an object while refusing ambiguous duplicate field names."""

    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result
