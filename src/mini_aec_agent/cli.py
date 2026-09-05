"""Command-line interface for interactive and one-shot questions."""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from mini_aec_agent.agent import AgentRunResult, run_agent
from mini_aec_agent.config import Settings, get_settings
from mini_aec_agent.exceptions import MiniAECError
from mini_aec_agent.logging_config import configure_logging
from mini_aec_agent.observability import configure_telemetry

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mini AEC Compliance Agent")
    parser.add_argument("-q", "--question", help="Run one question and exit.")
    parser.add_argument(
        "--trace", action="store_true", help="Print the machine-readable tool trace."
    )
    parser.add_argument(
        "--ifc",
        type=Path,
        help="Use this IFC model for IFC-aware questions.",
    )
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def _ask(question: str, show_trace: bool, settings: Settings) -> None:
    response = run_agent(question, return_trace=show_trace, settings=settings)

    if isinstance(response, dict):
        result: AgentRunResult = response
        print(result["answer"])
        print("\nTrace:")
        print(json.dumps(result["trace"], indent=2, ensure_ascii=False))
    else:
        print(response)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    if args.ifc is not None:
        settings = replace(settings, ifc_file=args.ifc.expanduser().resolve())
    configure_logging(args.log_level or settings.log_level, settings.log_format)
    configure_telemetry(settings)

    try:
        if args.question:
            _ask(args.question, args.trace, settings)
            return 0

        print("Mini AEC Compliance Agent")
        print("Type 'exit' to quit.\n")

        while True:
            question = input("You: ").strip()
            if question.casefold() in {"exit", "quit"}:
                print("Goodbye!")
                return 0
            if not question:
                continue

            print("\nAgent:")
            _ask(question, args.trace, settings)
            print()
    except (EOFError, KeyboardInterrupt):
        print("\nGoodbye!")
        return 0
    except MiniAECError as error:
        logger.error("%s", error)
        return 2
    except ValueError as error:
        logger.error("Invalid input: %s", error)
        return 2
    except Exception as error:
        logger.error("Unexpected failure: %s", type(error).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
