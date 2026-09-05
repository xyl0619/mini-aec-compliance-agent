"""Small, safe file-output helpers."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_text(
    output_file: str | Path, text: str, *, encoding: str = "utf-8"
) -> Path:
    """Atomically replace a text file after fully writing it in the same directory."""

    output_path = Path(output_file).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding=encoding,
            newline="\n",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(text)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, output_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            try:
                temporary_path.unlink()
            except OSError:
                # Preserve the original write error if temporary cleanup also fails.
                pass
    return output_path
