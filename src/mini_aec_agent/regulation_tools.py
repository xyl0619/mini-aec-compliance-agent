"""Agent-facing regulation retrieval tools."""

from __future__ import annotations

from typing import Any

from mini_aec_agent.config import Settings, get_settings
from mini_aec_agent.regulations.retriever import RegulationRetriever


def retrieve_regulations(
    query: str, top_k: int = 5, settings: Settings | None = None
) -> dict[str, Any]:
    """Retrieve regulation evidence with stable page-level citations."""

    active_settings = settings or get_settings()
    retriever = RegulationRetriever(active_settings.regulation_index_file)
    return retriever.retrieve(query, top_k)
