from __future__ import annotations

import json
from typing import Any

from core.groq_client import call_llm
from core.state import AgentState


class Verifier:
    def verify_step(self, step: dict[str, Any], state: AgentState) -> tuple[bool, str]:
        prompt = (
            "Decide whether this execution step is complete.\n"
            f"Task: {state.task}\n"
            f"Workspace: {state.workspace_dir}\n"
            f"Step: {step}\n"
            f"Completed steps: {state.completed_steps}\n"
            'Return strict JSON with {"complete": true, "reason": "short explanation"} only.'
        )
        try:
            response = call_llm(
                messages=[{"role": "user", "content": prompt}],
                system_prompt="You verify local agent execution. Return JSON only.",
                json_output=True,
            )
            payload = self.extract_json(response["choices"][0]["message"]["content"])
            return bool(payload.get("complete")), str(payload.get("reason", "No reason provided."))
        except Exception as exc:
            return False, f"Verification failed: {exc}"

    def verify_task(self, task: str, completed_steps: list[dict[str, Any]]) -> tuple[bool, str]:
        prompt = (
            "Decide whether the overall task is complete.\n"
            f"Task: {task}\n"
            f"Completed steps: {completed_steps}\n"
            'Return strict JSON with {"complete": true, "reason": "short explanation"} only.'
        )
        try:
            response = call_llm(
                messages=[{"role": "user", "content": prompt}],
                system_prompt="You verify whether a task is fully complete. Return JSON only.",
                json_output=True,
            )
            payload = self.extract_json(response["choices"][0]["message"]["content"])
            return bool(payload.get("complete")), str(payload.get("reason", "No reason provided."))
        except Exception as exc:
            return False, f"Task verification failed: {exc}"

    @staticmethod
    def extract_json(content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3:
                text = "\n".join(lines[1:-1]).strip()
        return json.loads(text)


TaskVerifier = Verifier
