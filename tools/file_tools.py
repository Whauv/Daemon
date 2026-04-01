from __future__ import annotations

from pathlib import Path


def _resolve_workspace_path(path: str, workspace: str) -> Path:
    requested = Path(path)
    if requested.is_absolute():
        raise ValueError("Absolute paths are not allowed.")

    raw_parts = requested.parts
    if any(part == ".." for part in raw_parts):
        raise ValueError("Path traversal is not allowed.")

    workspace_path = Path(workspace).resolve()
    resolved = (workspace_path / requested).resolve()

    try:
        resolved.relative_to(workspace_path)
    except ValueError as exc:
        raise ValueError("Resolved path escapes the workspace.") from exc

    return resolved


def write_file(path: str, content: str, workspace: str) -> bool:
    try:
        target = _resolve_workspace_path(path, workspace)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return True
    except Exception:
        return False


def create_dir(path: str, workspace: str) -> bool:
    try:
        target = _resolve_workspace_path(path, workspace)
        target.mkdir(parents=True, exist_ok=True)
        return True
    except Exception:
        return False


def read_file(path: str, workspace: str) -> str:
    try:
        target = _resolve_workspace_path(path, workspace)
        return target.read_text(encoding="utf-8")
    except Exception as exc:
        return f"ERROR: {exc}"


def list_dir(path: str, workspace: str) -> list[str]:
    target = _resolve_workspace_path(path, workspace)
    if not target.exists():
        return []
    if not target.is_dir():
        raise ValueError("Target path is not a directory.")
    return sorted(entry.name for entry in target.iterdir())


def delete_file(path: str, workspace: str) -> bool:
    try:
        target = _resolve_workspace_path(path, workspace)
        if target.exists() and target.is_file():
            target.unlink()
            return True
        return False
    except Exception:
        return False
