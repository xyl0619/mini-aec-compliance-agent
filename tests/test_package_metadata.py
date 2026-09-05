from __future__ import annotations

import tomllib
from pathlib import Path

from mini_aec_agent import __version__


def test_package_version_and_console_scripts_are_consistent() -> None:
    project_root = Path(__file__).resolve().parents[1]
    metadata = tomllib.loads(
        (project_root / "pyproject.toml").read_text(encoding="utf-8")
    )

    assert metadata["project"]["version"] == __version__
    assert metadata["project"]["requires-python"] == ">=3.11,<3.14"
    assert metadata["project"]["scripts"] == {
        "mini-aec-agent": "mini_aec_agent.cli:main",
        "mini-aec-api": "mini_aec_agent.api.app:run",
    }
