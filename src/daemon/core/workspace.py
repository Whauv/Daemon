from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from daemon.core.errors import InvalidRequestError

# Folders that hold tooling or runtime state rather than generated project code.
IGNORED_WORKSPACE_DIRS = frozenset(
    {
        "__pycache__",
        ".git",
        ".idea",
        ".vscode",
        ".venv",
        "venv",
        "node_modules",
        ".daemon",
    }
)

# Hidden folder inside a workspace where Daemon keeps its own artifacts
# (per-run session logs, launch logs). Hidden folders are never listed as projects.
DAEMON_STATE_DIRNAME = ".daemon"


def is_ignored_path(path: Path) -> bool:
    return any(part in IGNORED_WORKSPACE_DIRS for part in path.parts)


def iter_project_files(root: Path, pattern: str = "*") -> Iterator[Path]:
    """Yield files below ``root`` while skipping virtualenvs, caches, and Daemon state."""
    for path in root.rglob(pattern):
        if is_ignored_path(path.relative_to(root)):
            continue
        if path.is_file():
            yield path


def ensure_workspace_root(path: str | Path) -> Path:
    root = Path(path).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_dashboard_workspace(requested_workspace: str | None, workspace_root: str | Path) -> Path:
    root = ensure_workspace_root(workspace_root)
    if not requested_workspace:
        return root

    candidate = Path(requested_workspace)
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    _ensure_within_root(resolved, root)
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def resolve_project_directory(
    project_name: str,
    *,
    workspace_dir: str | Path,
    workspace_root: str | Path,
) -> Path:
    workspace = resolve_dashboard_workspace(str(workspace_dir), workspace_root)
    project_path = (workspace / project_name).resolve()
    _ensure_within_root(project_path, workspace)
    if project_path == workspace:
        raise InvalidRequestError("A project name is required.")
    return project_path


def list_visible_project_directories(workspace_dir: str | Path) -> list[Path]:
    root = ensure_workspace_root(workspace_dir)
    projects: list[Path] = []
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        if entry.name.startswith(".") or entry.name in IGNORED_WORKSPACE_DIRS:
            continue
        projects.append(entry)
    return sorted(projects, key=lambda item: item.name.lower())


def _ensure_within_root(candidate: Path, root: Path) -> None:
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise InvalidRequestError(f"Workspace path must stay inside {root}") from exc
