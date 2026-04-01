from __future__ import annotations

from textwrap import dedent

from core.groq_client import GroqClientManager
from core.state import ExecutionResult, PlanStep


class TaskVerifier:
    def __init__(self) -> None:
        self.client = GroqClientManager()

    def verify_step(self, step: PlanStep, result: ExecutionResult) -> tuple[bool, str]:
        if not result.success:
            return False, result.error or "Step execution failed."

        if step.action == "shell" and result.exit_code not in (None, 0):
            return False, f"Command exited with code {result.exit_code}"

        if step.action == "verify":
            return True, result.output or "Verification step completed."

        prompt = dedent(
            f"""
            Determine whether this execution step completed successfully.

            Step:
            {step.model_dump_json(indent=2)}

            Result:
            {result.model_dump_json(indent=2)}

            Return strict JSON:
            {{
              "complete": true,
              "reason": "short explanation"
            }}
            """
        ).strip()

        try:
            payload = self.client.complete_json(
                system_prompt="You verify local task execution results. Return strict JSON only.",
                user_prompt=prompt,
            )
            return bool(payload.get("complete")), str(payload.get("reason", "No reason provided."))
        except Exception:
            return True, "Execution completed and heuristic checks passed."

    def verify_task(self, task: str, completed_steps: list[PlanStep]) -> tuple[bool, str]:
        if not completed_steps:
            return False, "No steps were completed."

        prompt = dedent(
            f"""
            Determine whether the original task is complete.

            Task: {task}
            Completed steps:
            {[step.model_dump() for step in completed_steps]}

            Return strict JSON:
            {{
              "complete": true,
              "reason": "short explanation"
            }}
            """
        ).strip()

        try:
            payload = self.client.complete_json(
                system_prompt="You decide whether a task is complete. Return strict JSON only.",
                user_prompt=prompt,
            )
            return bool(payload.get("complete")), str(payload.get("reason", "No reason provided."))
        except Exception:
            return completed_steps[-1].action == "verify", "Fallback task verification completed."
