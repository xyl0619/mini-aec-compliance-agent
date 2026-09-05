"""Generate a JSON compliance report for a configured IFC file."""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from mini_aec_agent.config import get_settings
from mini_aec_agent.reports import build_ifc_compliance_report, write_json_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an IFC compliance report.")
    parser.add_argument("--ifc", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--global-id", action="append", dest="global_ids")
    args = parser.parse_args()

    settings = replace(get_settings(), ifc_file=args.ifc.expanduser().resolve())
    report = build_ifc_compliance_report(args.global_ids, settings)
    output_path = write_json_report(report, args.output)
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
