from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from daemon.core.groq_client import call_llm, extract_json
from daemon.core.state import AgentState
from daemon.core.workspace import iter_project_files
from daemon.tools.file_tools import read_file
from daemon.tools.shell_tools import run_command

API_TASK_PATTERN = re.compile(r"\b(fastapi|apis?)\b")
FILE_STEP_TYPES = {"write_file", "create_dir"}


class Verifier:
    def verify_step(self, step: dict[str, Any], state: AgentState) -> bool:
        step_type = step.get("type", "")
        args = step.get("args", {})

        if step_type == "verify" and isinstance(args.get("command"), str) and args["command"].strip():
            result = run_command(args["command"], state.workspace_dir)
            return result["exit_code"] == 0

        if step_type == "write_file":
            path = str(args.get("path", ""))
            content = read_file(path, state.workspace_dir)
            return bool(content) and not content.startswith("ERROR:")

        if step_type == "run_command":
            output = str(step.get("output", ""))
            forbidden_markers = ("error", "traceback", "failed")
            lowered_output = output.lower()
            return not any(marker in lowered_output for marker in forbidden_markers)

        if isinstance(args.get("command"), str) and args["command"].strip():
            result = run_command(args["command"], state.workspace_dir)
            return result["exit_code"] == 0

        return step.get("status") == "done"

    def verify_task(self, state: AgentState) -> dict[str, Any]:
        heuristic_result = self._verify_task_from_workspace(state)
        if heuristic_result["success"]:
            return heuristic_result

        completed_outputs = [
            {
                "id": step.get("id"),
                "title": step.get("title"),
                "type": step.get("type"),
                "output": step.get("output", ""),
            }
            for step in state.completed_steps
        ]
        prompt = (
            "Given this task and these step outputs, is the task complete? Return JSON.\n"
            f"Task: {state.task}\n"
            f"Completed step outputs: {completed_outputs}"
        )
        try:
            response = call_llm(
                messages=[{"role": "user", "content": prompt}],
                system_prompt="You are a QA engineer. Return JSON: {success: bool, summary: str, issues: list[str]}",
                json_output=True,
            )
            return self.extract_json(response["choices"][0]["message"]["content"])
        # Best-effort LLM call: any SDK, network, or malformed-JSON failure is reported as a failed verification.
        except Exception as exc:  # noqa: BLE001
            return {
                "success": False,
                "summary": heuristic_result["summary"] or f"Task verification failed: {exc}",
                "issues": heuristic_result["issues"] or ["Unable to complete LLM-based task verification."],
            }

    def _verify_task_from_workspace(self, state: AgentState) -> dict[str, Any]:
        # Only inspect the project this run produced, so older projects in a shared
        # workspace cannot make a new run look complete.
        workspace_root = self._verification_root(state)
        python_files = self._workspace_python_files(str(workspace_root))
        package_json = workspace_root / "package.json"

        if self._looks_like_fastapi_task(state.task, python_files):
            return self._verify_fastapi_workspace(state, python_files)
        if self._looks_like_react_task(state.task, package_json):
            return self._verify_react_workspace(state, workspace_root, package_json)
        return self._verify_generic_workspace(state, workspace_root, python_files)

    def _verify_fastapi_workspace(self, state: AgentState, python_files: list[Path]) -> dict[str, Any]:
        if not python_files:
            return {
                "success": False,
                "summary": "No generated Python files were found in the workspace.",
                "issues": ["No Python application files were created."],
            }

        combined = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in python_files)
        lowered = combined.lower()

        endpoint_markers = ("@app.get(", "@app.post(", "@app.put(", "@app.delete(")
        found_endpoint_count = sum(lowered.count(marker) for marker in endpoint_markers)
        sqlite_markers = ("sqlite://", "sqlite3", "create_engine(", ".db")
        has_sqlite = any(marker in lowered for marker in sqlite_markers)
        has_fastapi = "fastapi" in lowered and "fastapi()" in lowered
        required_endpoints = self._required_endpoint_count(state.task)

        issues: list[str] = []
        if not has_fastapi:
            issues.append("No FastAPI application file found.")
        if found_endpoint_count < required_endpoints:
            issues.append(f"Expected at least {required_endpoints} endpoint decorators in the generated app.")
        if not has_sqlite and "sqlite" in state.task.lower():
            issues.append("No SQLite database setup found in the generated app.")

        if issues:
            return {
                "success": False,
                "summary": "Workspace verification found missing API or database pieces.",
                "issues": issues,
            }

        app_files = ", ".join(path.name for path in python_files)
        return {
            "success": True,
            "summary": f"Verified FastAPI workspace with {found_endpoint_count} endpoints in: {app_files}",
            "issues": [],
        }

    def _verify_react_workspace(self, state: AgentState, workspace_root: Path, package_json: Path) -> dict[str, Any]:
        issues: list[str] = []
        if not package_json.exists():
            issues.append("package.json was not created.")
            return {
                "success": False,
                "summary": "React workspace verification failed.",
                "issues": issues,
            }

        try:
            package_data = json.loads(package_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {
                "success": False,
                "summary": "React workspace verification failed.",
                "issues": ["package.json is not valid JSON."],
            }

        scripts = package_data.get("scripts", {})
        if "build" not in scripts:
            issues.append("package.json is missing a build script.")

        src_dir = workspace_root / "src"
        if not src_dir.exists():
            issues.append("src directory was not created.")

        app_files = [path for path in src_dir.rglob("*") if path.is_file()] if src_dir.exists() else []
        has_entry = any(path.name.lower().startswith("app.") for path in app_files)
        component_count = sum(path.suffix.lower() in {".js", ".jsx", ".ts", ".tsx", ".css"} for path in app_files)

        if not has_entry:
            issues.append("No App entry file was found in src.")
        if component_count < 2:
            issues.append("The React workspace does not contain enough source files to represent a usable app.")

        if issues:
            return {
                "success": False,
                "summary": "React workspace verification found missing project structure.",
                "issues": issues,
            }

        return {
            "success": True,
            "summary": f"Verified React workspace with {component_count} source files and a build script.",
            "issues": [],
        }

    def _verify_generic_workspace(
        self,
        state: AgentState,
        workspace_root: Path,
        python_files: list[Path],
    ) -> dict[str, Any]:
        generated_files = [
            path for path in iter_project_files(workspace_root)
            if path.name != "daemon_session_log.json"
        ]
        if not generated_files:
            return {
                "success": False,
                "summary": "No generated files were found in the workspace.",
                "issues": ["The workspace is empty."],
            }

        if state.failed_steps and not state.completed_steps:
            return {
                "success": False,
                "summary": "Execution produced no successful steps.",
                "issues": ["All recorded steps failed."],
            }

        primary_files = ", ".join(path.name for path in generated_files[:5])
        return {
            "success": True,
            "summary": f"Verified generated workspace contents including: {primary_files}",
            "issues": [],
        }

    @staticmethod
    def _workspace_python_files(workspace_dir: str) -> list[Path]:
        return list(iter_project_files(Path(workspace_dir), "*.py"))

    @staticmethod
    def _verification_root(state: AgentState) -> Path:
        """Return the single project folder this run wrote into, else the workspace root."""
        workspace = Path(state.workspace_dir)
        top_level: set[str] = set()
        for step in state.completed_steps:
            if step.get("type") not in FILE_STEP_TYPES:
                continue
            raw = str(step.get("args", {}).get("path", "")).replace("\\", "/").strip()
            parts = PurePosixPath(raw).parts
            if not parts or parts[0] in {"/", "..", "."}:
                continue
            if step.get("type") == "write_file" and len(parts) == 1:
                return workspace  # The run wrote straight into the workspace root.
            top_level.add(parts[0])
        if len(top_level) == 1:
            candidate = workspace / top_level.pop()
            if candidate.is_dir():
                return candidate
        return workspace

    @staticmethod
    def _looks_like_fastapi_task(task: str, python_files: list[Path]) -> bool:
        if API_TASK_PATTERN.search(task.lower()):
            return True
        return any("fastapi" in path.read_text(encoding="utf-8", errors="ignore").lower() for path in python_files)

    @staticmethod
    def _looks_like_react_task(task: str, package_json: Path) -> bool:
        task_lower = task.lower()
        if "react" in task_lower or "frontend" in task_lower:
            return True
        return package_json.exists()

    @staticmethod
    def _required_endpoint_count(task: str) -> int:
        task_lower = task.lower()
        match = re.search(r"(\d+)\s+endpoints?", task_lower)
        if match:
            return max(1, int(match.group(1)))
        if "crud" in task_lower:
            return 4
        return 1

    @staticmethod
    def extract_json(content: str) -> dict[str, Any]:
        return extract_json(content)
