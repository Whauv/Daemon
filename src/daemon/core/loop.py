from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Protocol

from daemon.agents.executor import Executor
from daemon.agents.planner import Planner
from daemon.agents.verifier import Verifier
from daemon.core.state import AgentState
from daemon.ui.display import DaemonDisplay


EventHandler = Callable[[dict[str, Any]], None]
CancelHandler = Callable[[], bool]


class PlannerContract(Protocol):
    def generate_plan(self, task: str, workspace_dir: str) -> list[dict[str, Any]]: ...
    def replan_step(self, failed_step: dict[str, Any], state: AgentState) -> dict[str, Any]: ...
    def generate_patch_plan(self, issues: list[str], state: AgentState) -> list[dict[str, Any]]: ...


class ExecutorContract(Protocol):
    def execute_step(self, step: dict[str, Any], state: AgentState) -> dict[str, Any]: ...


class VerifierContract(Protocol):
    def verify_task(self, state: AgentState) -> dict[str, Any]: ...


def save_session_log(state: AgentState, workspace_dir: str) -> Path:
    log_path = Path(workspace_dir) / "daemon_session_log.json"
    log_path.write_text(state.model_dump_json(indent=2), encoding="utf-8")
    return log_path


def _emit(event_handler: EventHandler | None, event: dict[str, Any]) -> None:
    if event_handler is not None:
        event_handler(event)


def generate_plan_snapshot(task: str, workspace_dir: str) -> list[dict[str, Any]]:
    planner = Planner(display=None)
    return planner.generate_plan(task=task, workspace_dir=workspace_dir)


def run(
    task: str,
    workspace_dir: str,
    max_retries: int | None = None,
    display: DaemonDisplay | None = None,
    event_handler: EventHandler | None = None,
    should_cancel: CancelHandler | None = None,
    planner: PlannerContract | None = None,
    executor: ExecutorContract | None = None,
    verifier: VerifierContract | None = None,
) -> AgentState:
    planner = planner or Planner(display=display)
    executor = executor or Executor()
    verifier = verifier or Verifier()
    state = AgentState(task=task, workspace_dir=str(Path(workspace_dir).resolve()))
    if max_retries is not None:
        state.max_retries = max_retries

    if display is not None:
        display.show_banner()
        display.show_status("Planning task...")
    _emit(event_handler, {"type": "status", "message": "Planning task..."})
    state.plan = planner.generate_plan(task, state.workspace_dir)
    state.status = "executing"
    if display is not None:
        display.show_plan(state.plan, task_name=state.task)
    _emit(event_handler, {"type": "plan", "task": state.task, "plan": state.plan})

    while state.current_step_index < len(state.plan):
        if should_cancel is not None and should_cancel():
            state.status = "cancelled"
            _emit(event_handler, {"type": "cancelled", "message": "Run cancelled before next step.", "state": state.model_dump()})
            break

        step = state.plan[state.current_step_index]
        if display is not None:
            display.show_step_start(step)
        _emit(event_handler, {"type": "step_start", "step": step, "state": state.model_dump()})

        updated_step = executor.execute_step(step, state)
        state.plan[state.current_step_index] = updated_step

        if updated_step["status"] == "failed":
            state.retries += 1
            if display is not None:
                display.show_step_failed(updated_step)
            _emit(
                event_handler,
                {"type": "step_failed", "step": updated_step, "retries": state.retries, "state": state.model_dump()},
            )
            if state.retries >= state.max_retries:
                state.status = "failed"
                if display is not None:
                    display.show_fatal_error("Max retries reached")
                _emit(event_handler, {"type": "fatal", "message": "Max retries reached", "state": state.model_dump()})
                break

            new_step = planner.replan_step(updated_step, state)
            new_step["id"] = step["id"]
            state.plan[state.current_step_index] = new_step
            _emit(event_handler, {"type": "step_replanned", "step": new_step, "state": state.model_dump()})
            continue

        state.retries = 0
        if display is not None:
            display.show_step_done(updated_step)
        _emit(event_handler, {"type": "step_done", "step": updated_step, "state": state.model_dump()})
        state.current_step_index += 1

        if should_cancel is not None and should_cancel():
            state.status = "cancelled"
            _emit(event_handler, {"type": "cancelled", "message": "Run cancelled after step completion.", "state": state.model_dump()})
            break

        if state.current_step_index >= len(state.plan) and state.status != "failed":
            state.status = "verifying"
            _emit(event_handler, {"type": "status", "message": "Verifying task...", "state": state.model_dump()})
            result = verifier.verify_task(state)
            if result["success"]:
                state.status = "done"
                if display is not None:
                    display.show_success(result["summary"])
                _emit(event_handler, {"type": "success", "result": result, "state": state.model_dump()})
                break

            if display is not None:
                display.show_issues(result["issues"])
            _emit(event_handler, {"type": "issues", "result": result, "state": state.model_dump()})
            if state.retries < state.max_retries:
                patch_plan = planner.generate_patch_plan(result["issues"], state)
                if patch_plan:
                    state.plan.extend(patch_plan)
                    if display is not None:
                        display.show_plan(state.plan, task_name=state.task)
                    state.retries += 1
                    state.status = "executing"
                    _emit(event_handler, {"type": "patch_plan", "plan": state.plan, "state": state.model_dump()})
                    continue
            state.status = "failed"
            _emit(event_handler, {"type": "failed", "result": result, "state": state.model_dump()})
            break

    session_log = save_session_log(state, state.workspace_dir)
    _emit(event_handler, {"type": "session_saved", "path": str(session_log), "state": state.model_dump()})
    return state


class DaemonLoop:
    def __init__(self, display: DaemonDisplay | None = None, workspace: Path | None = None) -> None:
        self.display = display or DaemonDisplay()
        self.workspace = workspace or Path.cwd()

    def run(self, task: str, max_iterations: int | None = None) -> AgentState:
        return run(task=task, workspace_dir=str(self.workspace), max_retries=max_iterations, display=self.display)
