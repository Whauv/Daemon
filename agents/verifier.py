from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.groq_client import call_llm
from core.state import AgentState
from tools.file_tools import read_file
from tools.shell_tools import run_command


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
        except Exception as exc:
            return {
                "success": False,
                "summary": heuristic_result["summary"] or f"Task verification failed: {exc}",
                "issues": heuristic_result["issues"] or ["Unable to complete LLM-based task verification."],
            }

    def _verify_task_from_workspace(self, state: AgentState) -> dict[str, Any]:
        python_files = self._workspace_python_files(state.workspace_dir)
        if not python_files:
            return {
                "success": False,
                "summary": "No generated Python files were found in the workspace.",
                "issues": ["No Python application files were created."],
            }

        combined = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in python_files)
        lowered = combined.lower()

        endpoint_markers = ("@app.get(", "@app.post(", "@app.put(", "@app.delete(")
        found_markers = [marker for marker in endpoint_markers if marker in lowered]
        sqlite_markers = ("sqlite://", "sqlite3", "create_engine(", ".db")
        has_sqlite = any(marker in lowered for marker in sqlite_markers)
        has_fastapi = "fastapi" in lowered and "fastapi()" in lowered

        issues: list[str] = []
        if not has_fastapi:
            issues.append("No FastAPI application file found.")
        if len(found_markers) < 4:
            issues.append("Expected at least four CRUD endpoint decorators in the generated app.")
        if not has_sqlite:
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
            "summary": f"Verified FastAPI CRUD app with SQLite setup in: {app_files}",
            "issues": [],
        }

    @staticmethod
    def _workspace_python_files(workspace_dir: str) -> list[Path]:
        root = Path(workspace_dir)
        files: list[Path] = []
        for path in root.rglob("*.py"):
            if "venv" in path.parts or "__pycache__" in path.parts:
                continue
            files.append(path)
        return files

    @staticmethod
    def extract_json(content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3:
                text = "\n".join(lines[1:-1]).strip()
        return json.loads(text)


TaskVerifier = Verifier
