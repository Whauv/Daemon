from __future__ import annotations

from pathlib import Path


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def list_dir(path: Path) -> list[str]:
    return sorted(str(entry) for entry in path.iterdir())


def delete_file(path: Path) -> None:
    if path.exists():
        path.unlink()
