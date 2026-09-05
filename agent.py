"""Backward-compatible imports for the packaged agent implementation."""

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from mini_aec_agent.agent import (  # noqa: E402
    MAX_AGENT_STEPS,
    MODEL_NAME,
    MODEL_SEED,
    MODEL_TEMPERATURE,
    RETRY_DELAYS,
    SYSTEM_PROMPT,
    TOOLS,
    call_model,
    execute_tool,
    run_agent,
)

__all__ = [
    "MAX_AGENT_STEPS",
    "MODEL_NAME",
    "MODEL_SEED",
    "MODEL_TEMPERATURE",
    "RETRY_DELAYS",
    "SYSTEM_PROMPT",
    "TOOLS",
    "call_model",
    "execute_tool",
    "run_agent",
]
