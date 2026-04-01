from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from core.groq_client import call_llm
from core.state import PlanStep
from ui.display import DaemonDisplay


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
        steps = self._normalize_plan(steps)
        self._ensure_final_verify_step(steps)
        if self.display is not None:
            self.display.show_plan(steps, title="Generated Plan")
        return steps

    def replan_step(self, failed_step: dict[str, Any], state: Any) -> dict[str, Any]:
        messages = [
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
        response = call_llm(
            messages=messages,
            system_prompt=PLANNER_SYSTEM_PROMPT,
            temperature=0.2,
            json_output=True,
        )
        payload = PlanResponse.model_validate_json(response["choices"][0]["message"]["content"])
        if not payload.steps:
            raise ValueError("Replan response did not include any steps.")
        replacement = self._validate_step(payload.steps[0])
        replacement["id"] = failed_step["id"]
        return self._normalize_plan([replacement])[0]

    def generate_patch_plan(self, issues: list[str], state: Any) -> list[dict[str, Any]]:
        messages = [
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
        ]
        response = call_llm(
            messages=messages,
            system_prompt=PLANNER_SYSTEM_PROMPT,
            temperature=0.2,
            json_output=True,
        )
        payload = PlanResponse.model_validate_json(response["choices"][0]["message"]["content"])
        steps = [self._validate_step(step) for step in payload.steps]
        steps = self._normalize_plan(steps)
        self._ensure_final_verify_step(steps)
        return steps

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
    def _infer_project_dir(steps: list[dict[str, Any]]) -> str:
        for step in steps:
            if step.get("type") == "create_dir":
                path = str(step.get("args", {}).get("path", "")).strip()
                if path:
                    return path
        for step in steps:
            if step.get("type") == "write_file":
                path = str(step.get("args", {}).get("path", "")).replace("/", "\\")
                if "\\" in path:
                    return path.split("\\", 1)[0]
        return "project"

    @staticmethod
    def _relativize_path(path: str, project_dir: str) -> str:
        normalized = path.replace("/", "\\")
        workspace_marker = "\\workspace\\"
        if workspace_marker in normalized.lower():
            lowered = normalized.lower()
            index = lowered.index(workspace_marker) + len(workspace_marker)
            return normalized[index:]
        return normalized

    @staticmethod
    def _is_activation_command(command: str) -> bool:
        lowered = command.lower().strip()
        return lowered.endswith("\\scripts\\activate") or lowered.endswith("\\scripts\\activate.ps1")

    @staticmethod
    def _normalize_command(command: str, project_dir: str) -> str:
        normalized = command.replace("/", "\\").strip()
        lowered = normalized.lower()

        if "create-react-app" in lowered:
            return f"npm create vite@latest {project_dir} -- --template react"

        if lowered == "npm install":
            return f"cmd /c \"cd {project_dir} && npm install\""

        if lowered.startswith("npm install "):
            package_part = normalized[len("npm install") :].strip()
            return f"cmd /c \"cd {project_dir} && npm install {package_part}\""

        if lowered.startswith("npm run dev") or lowered.startswith("npm start"):
            return f"cmd /c \"cd {project_dir} && npm run build\""

        if lowered.startswith("npm run build"):
            return f"cmd /c \"cd {project_dir} && npm run build\""

        if lowered.startswith("pip install"):
            package_part = normalized[len("pip install") :].strip()
            return f"{project_dir}\\venv\\Scripts\\python.exe -m pip install {package_part}"

        if "uvicorn main:app" in lowered:
            return normalized.replace("uvicorn main:app", f"{project_dir}\\venv\\Scripts\\python.exe -m uvicorn app:app")

        return normalized

    @staticmethod
    def _normalize_verify_command(command: str, project_dir: str) -> str:
        normalized = command.replace("/", "\\").strip()
        lowered = normalized.lower()
        if "npm" in lowered:
            return f"cmd /c \"cd {project_dir} && npm run build\""
        if "uvicorn" in lowered or "curl" in lowered:
            return (
                f"{project_dir}\\venv\\Scripts\\python.exe -c "
                "\"import pathlib, sys; "
                f"sys.path.insert(0, str(pathlib.Path(r'{project_dir}').resolve())); "
                "from app import app; "
                "routes = [route.path for route in app.routes if hasattr(route, 'path')]; "
                "assert '/users/' in routes; "
                "print('verify ok')\""
            )
        return normalized

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
