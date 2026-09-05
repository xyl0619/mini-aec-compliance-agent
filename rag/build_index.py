"""Backward-compatible regulation index builder."""

from mini_aec_agent.config import get_settings
from mini_aec_agent.regulations.index import build_index as _build_index
from mini_aec_agent.regulations.index import main


def build_index():
    settings = get_settings()
    return _build_index(settings.regulation_pdf_file, settings.regulation_index_file)


if __name__ == "__main__":
    raise SystemExit(main())
