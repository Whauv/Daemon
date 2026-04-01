from __future__ import annotations

from pathlib import Path

from core.state import ExecutionResult, PlanStep
from tools.file_tools import list_dir, read_file, write_file, delete_file
from tools.shell_tools import run_command


class StepExecutor:
    def execute(self, step: PlanStep, workspace: Path) -> ExecutionResult:
        try:
            if step.action == "shell":
                result = run_command(step.command or "", cwd=workspace)
                return ExecutionResult(
                    success=result["exit_code"] == 0,
                    step_id=step.id,
                    action=step.action,
                    output=result["stdout"],
                    error=result["stderr"],
                    exit_code=result["exit_code"],
                )

            if step.action == "write_file":
                if not step.target:
                    raise ValueError("write_file step requires a target path")
                file_path = workspace / step.target
                write_file(file_path, step.content or "")
                return ExecutionResult(
                    success=True,
                    step_id=step.id,
                    action=step.action,
                    output=f"Wrote file: {file_path}",
                )

            if step.action == "inspect":
                listing = list_dir(workspace)
                return ExecutionResult(
                    success=True,
                    step_id=step.id,
                    action=step.action,
                    output="\n".join(listing),
                )

            if step.action == "read_file":
                if not step.target:
                    raise ValueError("read_file step requires a target path")
                content = read_file(workspace / step.target)
                return ExecutionResult(
                    success=True,
                    step_id=step.id,
                    action=step.action,
                    output=content,
                )

            if step.action == "delete_file":
                if not step.target:
                    raise ValueError("delete_file step requires a target path")
                delete_file(workspace / step.target)
                return ExecutionResult(
                    success=True,
                    step_id=step.id,
                    action=step.action,
                    output=f"Deleted file: {step.target}",
                )

            if step.action == "verify":
                return ExecutionResult(
                    success=True,
                    step_id=step.id,
                    action=step.action,
                    output=step.verification or "Verification step queued.",
                )

            raise ValueError(f"Unsupported action: {step.action}")
        except Exception as exc:
            return ExecutionResult(
                success=False,
                step_id=step.id,
                action=step.action,
                error=str(exc),
                exit_code=1,
            )
