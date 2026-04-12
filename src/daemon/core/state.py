from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


StepType = Literal["write_file", "run_command", "create_dir", "verify"]
StepStatus = Literal["pending", "running", "done", "failed"]
AgentStatus = Literal["planning", "executing", "verifying", "done", "failed", "cancelled"]


class PlanStep(BaseModel):
    id: int
    title: str
    description: str
    type: StepType
    args: dict[str, Any] = Field(default_factory=dict)
    status: StepStatus = "pending"
    output: str = ""


class ExecutionResult(BaseModel):
    success: bool
    step_id: int
    output: str = ""
    error: str = ""
    exit_code: int | None = None


class AgentState(BaseModel):
    task: str
    plan: list[dict[str, Any]] = Field(default_factory=list)
    current_step_index: int = 0
    completed_steps: list[dict[str, Any]] = Field(default_factory=list)
    failed_steps: list[dict[str, Any]] = Field(default_factory=list)
    workspace_dir: str
    status: AgentStatus = "planning"
    retries: int = 0
    max_retries: int = 3
    conversation_history: list[dict[str, Any]] = Field(default_factory=list)

    def remaining_steps(self) -> list[dict[str, Any]]:
        return self.plan[self.current_step_index :]

    @staticmethod
    def create_step(
        *,
        id: int,
        title: str,
        description: str,
        type: StepType,
        args: dict[str, Any] | None = None,
        status: StepStatus = "pending",
        output: str = "",
    ) -> dict[str, Any]:
        return PlanStep(
            id=id,
            title=title,
            description=description,
            type=type,
            args=args or {},
            status=status,
            output=output,
        ).model_dump()
