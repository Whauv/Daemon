from __future__ import annotations

from pathlib import Path

from agents.executor import StepExecutor
from agents.planner import TaskPlanner
from agents.verifier import TaskVerifier
from core.state import AgentState, PlanStep
from ui.display import NexusDisplay


class NexusLoop:
    def __init__(self, display: NexusDisplay, workspace: Path) -> None:
        self.display = display
        self.workspace = workspace
        self.planner = TaskPlanner()
        self.executor = StepExecutor()
        self.verifier = TaskVerifier()

    def run(self, task: str, max_iterations: int) -> AgentState:
        state = AgentState(
            original_task=task,
            workspace=str(self.workspace),
            max_iterations=max_iterations,
            status="running",
        )

        state.plan = self.planner.create_plan(task=task, workspace=str(self.workspace))
        self.display.show_plan(state.plan)

        while state.iteration < state.max_iterations:
            if state.current_step_index >= len(state.plan):
                complete, reason = self.verifier.verify_task(task, state.completed_steps)
                state.last_verification = reason
                state.status = "completed" if complete else "failed"
                if not complete:
                    revised_steps = self.planner.replan(task, state.completed_steps, reason)
                    if revised_steps:
                        state.plan.extend(revised_steps)
                        self.display.log(f"Replanned remaining work: {reason}")
                        continue
                break

            step = state.plan[state.current_step_index]
            state.iteration += 1
            self.display.show_step_start(step, state.iteration, state.max_iterations)

            result = self.executor.execute(step=step, workspace=self.workspace)
            state.last_result = result
            self.display.show_step_result(step, result)

            is_complete, reason = self.verifier.verify_step(step, result)
            state.last_verification = reason
            state.logs.append(f"{step.id}: {reason}")

            if is_complete:
                state.completed_steps.append(step)
                state.current_step_index += 1
                self.display.log(f"Verified {step.id}: {reason}")
                continue

            state.failed_steps.append(step)
            self.display.log(f"Step failed verification: {reason}")

            revised_steps = self.planner.replan(task, state.completed_steps, reason)
            if revised_steps:
                remaining = state.plan[state.current_step_index + 1 :]
                state.plan = state.completed_steps + revised_steps + remaining
                state.current_step_index = len(state.completed_steps)
                self.display.show_plan(state.plan, title="Revised plan")
                continue

            state.status = "failed"
            break

        if state.status == "running":
            state.status = "completed" if state.current_step_index >= len(state.plan) else "failed"

        return state
