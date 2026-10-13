"""Helpers for serializing retrieval traces without overwriting artifacts."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


def write_retrieval_traces(
    traces: Iterable[Mapping[str, Any]],
    output_path: str | Path,
    *,
    overwrite: bool = False,
) -> int:
    """Write one retrieval trace per JSONL row and return the row count.

    The experiment artifact writer may call this helper.  Existing files are
    protected by default so a previous experiment is not silently replaced.
    """

    path = Path(output_path)
    if path.exists() and not overwrite:
        raise FileExistsError(f"Retrieval trace file already exists: {path}")

    rows = list(traces)
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise TypeError(f"Trace at index {index} must be a mapping")

    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "w" if overwrite else "x"
    with path.open(mode, encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
    return len(rows)
