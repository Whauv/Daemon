"""Request and response schemas for the dashboard API.

Response models allow extra keys so that additive fields never get silently
dropped, and so the JSON shape stays identical to what the manager returns.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

MIN_TASK_WORDS = 5
MAX_TASK_CHARS = 4_000
MAX_RETRIES_LIMIT = 10


class RunRequest(BaseModel):
    task: str = Field(min_length=5, max_length=MAX_TASK_CHARS)
    workspace_dir: str | None = Field(default=None, max_length=1_024)
    max_retries: int = Field(default=3, ge=1, le=MAX_RETRIES_LIMIT)
    dry_run: bool = False

    @field_validator("task")
    @classmethod
    def _strip_task(cls, value: str) -> str:
        return value.strip()

    @field_validator("workspace_dir")
    @classmethod
    def _blank_workspace_is_default(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @property
    def task_word_count(self) -> int:
        return len(self.task.split())


class _OpenModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class HealthView(BaseModel):
    status: str


class RunView(_OpenModel):
    id: str
    task: str
    workspace_dir: str
    max_retries: int
    dry_run: bool
    status: str
    plan: list[dict[str, Any]]
    state: dict[str, Any] | None
    session_log_path: str | None
    created_at: str
    updated_at: str
    error: str | None
    cancel_requested: bool


class RunEvent(_OpenModel):
    timestamp: str
    type: str | None = None


class SessionLogView(BaseModel):
    path: str
    content: str


class ProjectView(_OpenModel):
    name: str
    path: str
    has_app: bool
    requirements: bool


class ProjectFileView(BaseModel):
    path: str
    size: int


class FilePreviewView(BaseModel):
    path: str
    content: str
    truncated: bool
    binary: bool
    size: int
    message: str


class LaunchView(_OpenModel):
    project_name: str
    pid: int
    port: int
    url: str
    docs_url: str
    started_at: str
    running: bool | None = None
    exit_code: int | None = None
    log_path: str | None = None


class LaunchLogView(BaseModel):
    path: str
    content: str
    truncated: bool
