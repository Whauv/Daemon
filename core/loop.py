from __future__ import annotations

import json
from pathlib import Path

from agents.executor import Executor
from agents.planner import Planner
from agents.verifier import Verifier
from core.state import AgentState
from ui.display import NexusDisplay


def save_session_log(state: AgentState, workspace_dir: str) -> Path:
    log_path = Path(workspace_dir) / "nexus_session_log.json"
    log_path.write_text(state.model_dump_json(indent=2), encoding="utf-8")
    return log_path


def run(task: str, workspace_dir: str) -> AgentState:
    display = NexusDisplay()
    planner = Planner(display=display)
    executor = Executor()
    verifier = Verifier()
    state = AgentState(task=task, workspace_dir=str(Path(workspace_dir).resolve()))

    display.show_banner()
    display.show_status("Planning task...")
    state.plan = planner.generate_plan(task, state.workspace_dir)
    state.status = "executing"
    display.show_plan(state.plan, task_name=state.task)

    while state.current_step_index < len(state.plan):
        step = state.plan[state.current_step_index]
        display.show_step_start(step)

        updated_step = executor.execute_step(step, state)
        state.plan[state.current_step_index] = updated_step

        if updated_step["status"] == "failed":
            state.retries += 1
            display.show_step_failed(updated_step)
            if state.retries >= state.max_retries:
                state.status = "failed"
                display.show_fatal_error("Max retries reached")
                break

            new_step = planner.replan_step(updated_step, state)
            state.plan[state.current_step_index] = new_step
            continue

        state.retries = 0
        display.show_step_done(updated_step)
        state.current_step_index += 1

        if state.current_step_index >= len(state.plan) and state.status != "failed":
            state.status = "verifying"
            result = verifier.verify_task(state)
            if result["success"]:
                state.status = "done"
                display.show_success(result["summary"])
                break

            display.show_issues(result["issues"])
            if state.retries < state.max_retries:
                patch_plan = planner.generate_patch_plan(result["issues"], state)
                if patch_plan:
                    state.plan.extend(patch_plan)
                    display.show_plan(state.plan, task_name=state.task)
                    state.retries += 1
                    state.status = "executing"
                    continue
            state.status = "failed"
            break

    save_session_log(state, state.workspace_dir)
    return state


class NexusLoop:
    def __init__(self, display: NexusDisplay | None = None, workspace: Path | None = None) -> None:
        self.display = display or NexusDisplay()
        self.workspace = workspace or Path.cwd()

    def run(self, task: str, max_iterations: int | None = None) -> AgentState:
        state = run(task=task, workspace_dir=str(self.workspace))
        if max_iterations is not None:
            state.max_retries = max_iterations
        return state
