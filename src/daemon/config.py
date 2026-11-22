from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - python-dotenv is a declared dependency
    def load_dotenv(*args: object, **kwargs: object) -> bool:
        return False


PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parents[1]

# The repository-root .env is the documented location. The package-level file is
# still honoured for installs that relied on it. Existing environment variables
# always win because load_dotenv does not override them.
ENV_FILES: tuple[Path, ...] = (PROJECT_ROOT / ".env", PACKAGE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    GROQ_API_KEY: str
    MODEL_NAME: str
    MAX_RETRIES: int
    WORKSPACE_DIR: str
    REQUEST_TIMEOUT: int
    RETRY_BACKOFF_SECONDS: float
    MAX_REQUESTS_PER_MINUTE: int


def _read_number(environ: Mapping[str, str], name: str, default: str, kind: type[int | float]) -> int | float:
    raw = environ.get(name, default).strip()
    try:
        return kind(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be a {kind.__name__}, got {raw!r}.") from exc


def _resolve_workspace(raw: str | None, project_root: Path) -> str:
    if not raw:
        return str((project_root / "workspace").resolve())
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = project_root / candidate
    return str(candidate.resolve())


def build_settings(environ: Mapping[str, str], *, project_root: Path = PROJECT_ROOT) -> Settings:
    """Build settings from an environment mapping. Pure so it can be tested."""
    return Settings(
        GROQ_API_KEY=environ.get("GROQ_API_KEY", ""),
        MODEL_NAME=environ.get("MODEL_NAME", "llama-3.3-70b-versatile"),
        MAX_RETRIES=int(_read_number(environ, "MAX_RETRIES", "3", int)),
        WORKSPACE_DIR=_resolve_workspace(environ.get("WORKSPACE_DIR"), project_root),
        REQUEST_TIMEOUT=int(_read_number(environ, "REQUEST_TIMEOUT", "60", int)),
        RETRY_BACKOFF_SECONDS=float(_read_number(environ, "RETRY_BACKOFF_SECONDS", "2.0", float)),
        MAX_REQUESTS_PER_MINUTE=int(_read_number(environ, "MAX_REQUESTS_PER_MINUTE", "25", int)),
    )


for _env_file in ENV_FILES:
    load_dotenv(_env_file)

settings = build_settings(os.environ)

GROQ_API_KEY = settings.GROQ_API_KEY
MODEL_NAME = settings.MODEL_NAME
MAX_RETRIES = settings.MAX_RETRIES
WORKSPACE_DIR = settings.WORKSPACE_DIR
REQUEST_TIMEOUT = settings.REQUEST_TIMEOUT
RETRY_BACKOFF_SECONDS = settings.RETRY_BACKOFF_SECONDS
MAX_REQUESTS_PER_MINUTE = settings.MAX_REQUESTS_PER_MINUTE
