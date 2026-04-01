from __future__ import annotations

import json
from textwrap import dedent

from core.groq_client import GroqClientManager
from core.state import PlanStep


class TaskPlanner:
    def __init__(self) -> None:
        self.client = GroqClientManager()

    def create_plan(self, task: str, workspace: str) -> list[PlanStep]:
        prompt = dedent(
            f"""
            You are the planner for a local AI agent orchestrator named Nexus Agent.
            Break the task into executable JSON steps for a Python agent.

            Task: {task}
            Workspace: {workspace}

            Return valid JSON matching this schema:
            {{
              "steps": [
                {{
                  "id": "step-1",
                  "title": "Short title",
                  "description": "What to do",
                  "action": "shell|write_file|inspect|verify",
                  "target": "optional file path or command target",
                  "command": "optional shell command",
                  "content": "optional file content",
                  "verification": "how the step should be checked"
                }}
              ]
            }}

            Rules:
            - Prefer 3 to 8 steps.
            - Use write_file only when full file content is known.
            - Use shell for commands that can be run locally.
            - End with a verify step.
            - Return JSON only.
            """
        ).strip()

        try:
            payload = self.client.complete_json(
                system_prompt="You create concise execution plans in strict JSON.",
                user_prompt=prompt,
            )
            steps = payload.get("steps", [])
            return [PlanStep.model_validate(step) for step in steps]
        except Exception:
            return self._fallback_plan(task)

    def replan(self, task: str, completed_steps: list[PlanStep], feedback: str) -> list[PlanStep]:
        completed = json.dumps([step.model_dump() for step in completed_steps], indent=2)
        prompt = dedent(
            f"""
            The orchestrator needs a revised plan.
            Original task: {task}
            Completed steps: {completed}
            Feedback: {feedback}

            Return strict JSON with a "steps" array using the same schema as before.
            Focus only on the remaining work.
            """
        ).strip()

        try:
            payload = self.client.complete_json(
                system_prompt="You revise execution plans in strict JSON.",
                user_prompt=prompt,
            )
            return [PlanStep.model_validate(step) for step in payload.get("steps", [])]
        except Exception:
            return []

    def _fallback_plan(self, task: str) -> list[PlanStep]:
        return [
            PlanStep(
                id="step-1",
                title="Inspect workspace",
                description=f"Review the workspace before starting task: {task}",
                action="inspect",
                verification="Workspace contents were listed successfully.",
            ),
            PlanStep(
                id="step-2",
                title="Implement task",
                description="Perform the primary implementation work.",
                action="shell",
                command='echo "Fill in execution details for this task."',
                verification="The implementation command completed successfully.",
            ),
            PlanStep(
                id="step-3",
                title="Verify completion",
                description="Check whether the task is complete.",
                action="verify",
                verification="All requested work appears complete.",
            ),
        ]
