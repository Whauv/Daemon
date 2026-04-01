from __future__ import annotations

import json
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
                "summary": f"Task verification failed: {exc}",
                "issues": ["Unable to complete LLM-based task verification."],
            }

    @staticmethod
    def extract_json(content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3:
                text = "\n".join(lines[1:-1]).strip()
        return json.loads(text)


TaskVerifier = Verifier
