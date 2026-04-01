from __future__ import annotations

from pathlib import Path
from typing import Any

from agents.verifier import Verifier
from core.groq_client import call_llm
from core.state import AgentState, PlanStep
from tools.file_tools import create_dir, write_file
from tools.shell_tools import run_command


class Executor:
    def __init__(self) -> None:
        self.verifier = Verifier()

    def execute_step(self, step: dict[str, Any], state: AgentState) -> dict[str, Any]:
        validated_step = PlanStep.model_validate(step).model_dump()
        validated_step["status"] = "running"

        step_type = validated_step["type"]
        if step_type == "create_dir":
            updated_step = self._execute_create_dir(validated_step, state)
        elif step_type == "write_file":
            updated_step = self._execute_write_file(validated_step, state)
        elif step_type == "run_command":
            updated_step = self._execute_run_command(validated_step, state)
        elif step_type == "verify":
            updated_step = self._execute_verify(validated_step, state)
        else:
            updated_step = validated_step
            updated_step["status"] = "failed"
            updated_step["output"] = f"Unsupported step type: {step_type}"

        if updated_step["status"] == "done":
            state.completed_steps.append(updated_step)
        else:
            state.failed_steps.append(updated_step)

        state.current_step_index += 1
        return updated_step

    def _execute_create_dir(self, step: dict[str, Any], state: AgentState) -> dict[str, Any]:
        relative_path = step["args"].get("path", "")
        try:
            if create_dir(path=relative_path, workspace=state.workspace_dir):
                step["status"] = "done"
                step["output"] = f"Created directory: {relative_path}"
            else:
                step["status"] = "failed"
                step["output"] = f"Failed to create directory: {relative_path}"
        except Exception as exc:
            step["status"] = "failed"
            step["output"] = f"Failed to create directory {relative_path}: {exc}"
        return step

    def _execute_write_file(self, step: dict[str, Any], state: AgentState) -> dict[str, Any]:
        path = str(step["args"].get("path", ""))
        content = str(step["args"].get("content", ""))

        if self._content_looks_incomplete(content):
            content = self._regenerate_file_content(step=step, state=state, existing_content=content)
            step["args"]["content"] = content

        success = write_file(path=path, content=content, workspace=state.workspace_dir)
        if success:
            step["status"] = "done"
            step["output"] = f"Wrote file: {path}"
        else:
            step["status"] = "failed"
            step["output"] = f"Failed to write file: {path}"
        return step

    def _execute_run_command(self, step: dict[str, Any], state: AgentState) -> dict[str, Any]:
        command = str(step["args"].get("command", ""))
        result = run_command(command=command, workspace=state.workspace_dir)
        attempts = 0

        while result["exit_code"] != 0 and attempts < 2:
            fix_command = self._suggest_fix_command(step=step, state=state, failed_command=command, result=result)
            if not fix_command:
                break
            attempts += 1
            command = fix_command
            result = run_command(command=command, workspace=state.workspace_dir)

        if result["exit_code"] == 0:
            step["status"] = "done"
            step["output"] = result["stdout"] or "Command completed successfully."
        else:
            step["status"] = "failed"
            step["output"] = result["stderr"] or result["stdout"] or "Command failed."
        return step

    def _execute_verify(self, step: dict[str, Any], state: AgentState) -> dict[str, Any]:
        verification_command = step["args"].get("command")
        if isinstance(verification_command, str) and verification_command.strip():
            result = run_command(command=verification_command, workspace=state.workspace_dir)
            step["status"] = "done" if result["exit_code"] == 0 else "failed"
            step["output"] = result["stdout"] or result["stderr"] or step["args"].get("check", "")
            return step

        is_complete, reason = self.verifier.verify_step(step=step, state=state)
        step["status"] = "done" if is_complete else "failed"
        step["output"] = reason
        return step

    @staticmethod
    def _content_looks_incomplete(content: str) -> bool:
        lowered = content.lower()
        markers = ("# todo", "todo:", "...", "placeholder", "fill this in", "implement here")
        return any(marker in lowered for marker in markers)

    def _regenerate_file_content(
        self,
        *,
        step: dict[str, Any],
        state: AgentState,
        existing_content: str,
    ) -> str:
        prompt = (
            "Regenerate this file as complete, working code with no placeholders.\n"
            f"Task: {state.task}\n"
            f"Workspace: {state.workspace_dir}\n"
            f"Target path: {step['args'].get('path', '')}\n"
            f"File purpose: {step['description']}\n"
            f"Current content:\n{existing_content}\n"
            'Return strict JSON with {"content": "<full file contents>"} only.'
        )
        try:
            response = call_llm(
                messages=[{"role": "user", "content": prompt}],
                system_prompt="You produce complete, working source files with no placeholders. Return JSON only.",
                json_output=True,
            )
            content = response["choices"][0]["message"]["content"]
            payload = self.verifier.extract_json(content)
            regenerated = str(payload.get("content", "")).strip()
            return regenerated or existing_content
        except Exception:
            return existing_content

    def _suggest_fix_command(
        self,
        *,
        step: dict[str, Any],
        state: AgentState,
        failed_command: str,
        result: dict[str, str | int],
    ) -> str:
        prompt = (
            "A shell command failed during task execution. Suggest exactly one replacement shell command.\n"
            f"Task: {state.task}\n"
            f"Workspace: {state.workspace_dir}\n"
            f"Step: {step}\n"
            f"Failed command: {failed_command}\n"
            f"stdout: {result.get('stdout', '')}\n"
            f"stderr: {result.get('stderr', '')}\n"
            'Return strict JSON with {"command": "<replacement command>"} only.'
        )
        try:
            response = call_llm(
                messages=[{"role": "user", "content": prompt}],
                system_prompt="You repair failed shell commands. Return JSON only.",
                json_output=True,
            )
            content = response["choices"][0]["message"]["content"]
            payload = self.verifier.extract_json(content)
            return str(payload.get("command", "")).strip()
        except Exception:
            return ""


StepExecutor = Executor
