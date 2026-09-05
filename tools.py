"""Backward-compatible imports for deterministic compliance tools."""

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from mini_aec_agent.compliance import (  # noqa: E402
    check_item_compliance,
    compare_values,
    get_applicable_rules,
)
from mini_aec_agent.ifc_tools import (  # noqa: E402
    check_ifc_element_compliance,
    get_ifc_element,
    get_ifc_summary,
    list_ifc_elements,
)
from mini_aec_agent.regulation_tools import retrieve_regulations  # noqa: E402
from mini_aec_agent.tools import (  # noqa: E402
    get_item,
    list_items,
    load_building,
    load_regulations,
)

__all__ = [
    "check_ifc_element_compliance",
    "check_item_compliance",
    "compare_values",
    "get_ifc_element",
    "get_ifc_summary",
    "get_applicable_rules",
    "get_item",
    "list_ifc_elements",
    "list_items",
    "load_building",
    "load_regulations",
    "retrieve_regulations",
]
