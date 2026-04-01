from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from core.groq_client import call_llm
from core.state import PlanStep
from ui.display import NexusDisplay


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
Return ONLY valid JSON. No markdown. No explanation.
""".strip()


class Planner:
    def __init__(self, display: NexusDisplay | None = None) -> None:
        self.display = display or NexusDisplay()

    def generate_plan(self, task: str, workspace_dir: str) -> list[dict[str, Any]]:
        messages = [
            {
                "role": "user",
                "content": (
                    f"Task: {task}\n"
                    f"Workspace directory: {workspace_dir}\n"
                    "Return a dependency-aware implementation plan."
                ),
            }
        ]
        response = call_llm(
            messages=messages,
            system_prompt=PLANNER_SYSTEM_PROMPT,
            temperature=0.2,
            json_output=True,
        )
        content = response["choices"][0]["message"]["content"]
        payload = PlanResponse.model_validate_json(content)
        steps = [self._validate_step(step) for step in payload.steps]
        self._ensure_final_verify_step(steps)
        self.display.show_plan(steps, title="Generated Plan")
        return steps

    def _validate_step(self, step: PlanStep) -> dict[str, Any]:
        validated_step = PlanStep.model_validate(step.model_dump())
        self._validate_step_args(validated_step)
        return validated_step.model_dump()

    def _validate_step_args(self, step: PlanStep) -> None:
        args = step.args
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
            raise ValueError(f"Step {step.id} output must be a string.")

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


TaskPlanner = Planner
