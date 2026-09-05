"""Backward-compatible regulation PDF extraction entry point."""

from mini_aec_agent.config import get_settings
from mini_aec_agent.regulations.extract import extract_pdf_pages as _extract_pdf_pages


def extract_pdf_pages():
    return _extract_pdf_pages(get_settings().regulation_pdf_file)


def main() -> int:
    pages = extract_pdf_pages()
    print(f"Extracted {len(pages)} pages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
