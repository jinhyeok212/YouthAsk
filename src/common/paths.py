from __future__ import annotations

from pathlib import Path


# src/common/paths.py -> src/common -> src -> project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def resolve_project_path(value: str | Path) -> Path:
    """Resolve a path against the project root, not the current working directory.

    Absolute paths are preserved. Relative paths are interpreted from the
    repository/project root so team members can launch the runner from another
    working directory without breaking config paths.
    """
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (PROJECT_ROOT / path).resolve()


def resolve_cli_path(value: str | Path) -> Path:
    """Resolve a command-line path.

    For an explicitly supplied relative CLI path, prefer the user's current
    working directory when that file exists. Otherwise fall back to project root.
    """
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()

    cwd_candidate = (Path.cwd() / path).resolve()
    if cwd_candidate.exists():
        return cwd_candidate

    return resolve_project_path(path)
