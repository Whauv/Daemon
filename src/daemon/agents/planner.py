from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from daemon.agents import command_normalizer
from daemon.core.groq_client import call_llm
from daemon.core.state import PlanStep
from daemon.ui.display import DaemonDisplay

PLANNER_SYSTEM_PROMPT = """
You are an expert software engineer and project planner.
Given a task, you must return a JSON object with a single key "steps" containing an ordered array of steps to complete the task.
Each step must have: id (int), title (str), description (str), type (one of: write_file, run_command, create_dir, verify), args (dict), status ("pending"), output ("").

For type "write_file": args must include "path" (relative path) and "content" (full file content as string).
For type "run_command": args must include "command" (shell command string).
For type "create_dir": args must include "path" (relative directory path).
For type "verify": args must include "check" (description of what to verify) and optionally "command" (shell command whose exit code 0 = success).

Always end the plan with a verify step.
Be specific. Write real, working code in write_file steps. Do not use placeholders.
All paths must be relative to the workspace directory. Never use absolute paths.
Prefer create_dir over shell mkdir commands.
Do not add shell steps that only activate a virtual environment. Instead, invoke the venv Python directly in commands.
For Python projects, prefer commands like "project_dir\\venv\\Scripts\\python.exe -m pip install -r project_dir\\requirements.txt".
For FastAPI apps, write an app.py file and verify with a non-blocking import command, not a long-running uvicorn server process.
For React apps, never use create-react-app. Use a non-interactive Vite React scaffold command and verify with "npm run build".
Return ONLY valid JSON. No markdown. No explanation.
""".strip()


class Planner:
    def __init__(self, display: DaemonDisplay | None = None) -> None:
        self.display = display

    def generate_plan(self, task: str, workspace_dir: str) -> list[dict[str, Any]]:
        steps = self._request_steps(
            [
                {
                    "role": "user",
                    "content": (
                        f"Task: {task}\n"
                        f"Workspace directory: {workspace_dir}\n"
                        "Return a dependency-aware implementation plan."
                    ),
                }
            ]
        )
        steps = self._normalize_plan(steps)
        steps = self._assign_step_ids(steps)
        self._ensure_final_verify_step(steps)
        if self.display is not None:
            self.display.show_plan(steps, title="Generated Plan")
        return steps

    def replan_step(self, failed_step: dict[str, Any], state: Any) -> dict[str, Any]:
        steps = self._request_steps(
            [
                {
                    "role": "user",
                    "content": (
                        f"Original task: {state.task}\n"
                        f"Workspace directory: {state.workspace_dir}\n"
                        f"Failed step: {failed_step}\n"
                        f"Completed steps: {state.completed_steps}\n"
                        "Return one corrected replacement step."
                    ),
                }
            ]
        )
        replacement = self._normalize_plan([steps[0]])[0]
        replacement["id"] = failed_step["id"]
        return replacement

    def generate_patch_plan(self, issues: list[str], state: Any) -> list[dict[str, Any]]:
        steps = self._request_steps(
            {
                "role": "user",
                "content": (
                    f"Original task: {state.task}\n"
                    f"Workspace directory: {state.workspace_dir}\n"
                    f"Completed steps: {state.completed_steps}\n"
                    f"Known issues: {issues}\n"
                    "Return an ordered patch plan to fix only these issues."
                ),
            }
        )
        steps = self._normalize_plan(steps)
        start_at = max((int(step.get("id", 0)) for step in state.plan), default=0) + 1
        steps = self._assign_step_ids(steps, start_at=start_at)
        self._ensure_final_verify_step(steps)
        return steps

    def _request_steps(self, messages: list[dict[str, str]] | dict[str, str]) -> list[dict[str, Any]]:
        payload_messages = messages if isinstance(messages, list) else [messages]
        response = call_llm(
            messages=payload_messages,
            system_prompt=PLANNER_SYSTEM_PROMPT,
            temperature=0.2,
            json_output=True,
        )
        content = response["choices"][0]["message"]["content"]
        payload = PlanResponse.model_validate_json(content)
        if not payload.steps:
            raise ValueError("Planner response did not include any steps.")
        return [self._validate_step(step) for step in payload.steps]

    def _normalize_plan(self, steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        project_dir = self._infer_project_dir(steps)
        normalized: list[dict[str, Any]] = []

        for step in steps:
            updated = dict(step)
            updated["args"] = dict(step.get("args", {}))
            step_type = updated["type"]

            if step_type in {"create_dir", "write_file"} and "path" in updated["args"]:
                updated["args"]["path"] = self._relativize_path(str(updated["args"]["path"]), project_dir)

            if step_type == "run_command":
                command = str(updated["args"].get("command", ""))
                updated["args"]["command"] = self._normalize_command(command, project_dir)
                if self._is_activation_command(updated["args"]["command"]):
                    continue

            if step_type == "verify":
                command = str(updated["args"].get("command", ""))
                if command:
                    updated["args"]["command"] = self._normalize_verify_command(command, project_dir)

            normalized.append(updated)

        return normalized

    @staticmethod
    def _assign_step_ids(steps: list[dict[str, Any]], start_at: int = 1) -> list[dict[str, Any]]:
        for offset, step in enumerate(steps):
            step["id"] = start_at + offset
        return steps

    # Thin delegators to the pure helpers in ``command_normalizer``; kept as
    # staticmethods so existing callers and tests reference them unchanged.
    _infer_project_dir = staticmethod(command_normalizer.infer_project_dir)
    _relativize_path = staticmethod(command_normalizer.relativize_path)
    _is_activation_command = staticmethod(command_normalizer.is_activation_command)
    _normalize_command = staticmethod(command_normalizer.normalize_command)
    _normalize_verify_command = staticmethod(command_normalizer.normalize_verify_command)

    def _validate_step(self, step: PlanStep) -> dict[str, Any]:
        validated_step = PlanStep.model_validate(step.model_dump())
        self._validate_step_args(validated_step)
        return validated_step.model_dump()

    def _validate_step_args(self, step: PlanStep) -> None:
        if step.type == "write_file":
            self._require_args(step, "path", "content")
        elif step.type == "run_command":
            self._require_args(step, "command")
        elif step.type == "create_dir":
            self._require_args(step, "path")
        elif step.type == "verify":
            self._require_args(step, "check")
        else:
            raise ValueError(f"Unsupported step type: {step.type}")

        if step.status != "pending":
            raise ValueError(f"Step {step.id} must start with status 'pending'.")
        if not isinstance(step.output, str):
            raise TypeError(f"Step {step.id} output must be a string.")

    def _require_args(self, step: PlanStep, *keys: str) -> None:
        missing = [key for key in keys if key not in step.args or step.args[key] in ("", None)]
        if missing:
            raise ValueError(f"Step {step.id} is missing required args: {', '.join(missing)}")

    def _ensure_final_verify_step(self, steps: list[dict[str, Any]]) -> None:
        if not steps:
            raise ValueError("Planner returned an empty plan.")
        last_step = steps[-1]
        if last_step["type"] != "verify":
            raise ValueError("Planner response must end with a verify step.")


class PlanResponse(BaseModel):
    steps: list[PlanStep]
