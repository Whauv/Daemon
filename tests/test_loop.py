from __future__ import annotations

import json
import unittest
from pathlib import Path

from core.loop import run
from core.state import AgentState
from tests._helpers import cleanup_test_dir, make_test_dir


class StubPlanner:
    def __init__(self, plan: list[dict], replacement_step: dict | None = None, patch_plan: list[dict] | None = None) -> None:
        self.plan = plan
        self.replacement_step = replacement_step
        self.patch_plan = patch_plan or []
        self.replanned = False
        self.patch_requested_with: list[str] | None = None

    def generate_plan(self, task: str, workspace_dir: str) -> list[dict]:
        return [dict(step) for step in self.plan]

    def replan_step(self, failed_step: dict, state: AgentState) -> dict:
        self.replanned = True
        if self.replacement_step is None:
            raise AssertionError("Replacement step was not configured.")
        return dict(self.replacement_step)

    def generate_patch_plan(self, issues: list[str], state: AgentState) -> list[dict]:
        self.patch_requested_with = issues
        return [dict(step) for step in self.patch_plan]


class StubExecutor:
    def __init__(self, results: list[dict]) -> None:
        self.results = [dict(result) for result in results]
        self.calls: list[int] = []

    def execute_step(self, step: dict, state: AgentState) -> dict:
        self.calls.append(step["id"])
        if not self.results:
            raise AssertionError("No more executor results configured.")
        result = dict(self.results.pop(0))
        if result["status"] == "done":
            state.completed_steps.append(result)
        else:
            state.failed_steps.append(result)
        return result


class StubVerifier:
    def __init__(self, results: list[dict]) -> None:
        self.results = [dict(result) for result in results]

    def verify_task(self, state: AgentState) -> dict:
        if not self.results:
            raise AssertionError("No more verifier results configured.")
        return dict(self.results.pop(0))


def make_step(step_id: int, step_type: str, title: str) -> dict:
    args = {"path": f"project/file-{step_id}.txt"} if step_type in {"write_file", "create_dir"} else {"command": "echo ok"} if step_type == "run_command" else {"check": "verify"}
    if step_type == "write_file":
        args["content"] = "hello"
    if step_type == "verify":
        args = {"check": "verify task"}
    return {
        "id": step_id,
        "title": title,
        "description": title,
        "type": step_type,
        "args": args,
        "status": "pending",
        "output": "",
    }


class LoopTests(unittest.TestCase):
    def test_run_successful_flow_saves_session_log(self) -> None:
        temp_dir = make_test_dir("loop_success")
        try:
            planner = StubPlanner(plan=[make_step(1, "write_file", "Create file")])
            executor = StubExecutor(results=[{**make_step(1, "write_file", "Create file"), "status": "done", "output": "created"}])
            verifier = StubVerifier(results=[{"success": True, "summary": "all good", "issues": []}])
            events: list[dict] = []

            state = run(
                task="build a useful generated file workspace",
                workspace_dir=str(temp_dir),
                planner=planner,
                executor=executor,
                verifier=verifier,
                event_handler=events.append,
            )

            self.assertEqual(state.status, "done")
            self.assertTrue((Path(temp_dir) / "daemon_session_log.json").exists())
            self.assertTrue(any(event["type"] == "success" for event in events))
        finally:
            cleanup_test_dir(temp_dir)

    def test_run_replans_failed_step_and_retries_same_index(self) -> None:
        temp_dir = make_test_dir("loop_replan")
        try:
            planner = StubPlanner(
                plan=[make_step(1, "run_command", "Initial command")],
                replacement_step=make_step(999, "run_command", "Replacement command"),
            )
            executor = StubExecutor(
                results=[
                    {**make_step(1, "run_command", "Initial command"), "status": "failed", "output": "boom"},
                    {**make_step(1, "run_command", "Replacement command"), "status": "done", "output": "fixed"},
                ]
            )
            verifier = StubVerifier(results=[{"success": True, "summary": "fixed", "issues": []}])

            state = run(
                task="repair a failing shell step for a project",
                workspace_dir=str(temp_dir),
                max_retries=2,
                planner=planner,
                executor=executor,
                verifier=verifier,
            )

            self.assertEqual(state.status, "done")
            self.assertTrue(planner.replanned)
            self.assertEqual(executor.calls, [1, 1])
            self.assertEqual(state.plan[0]["id"], 1)
        finally:
            cleanup_test_dir(temp_dir)

    def test_run_generates_patch_plan_after_failed_verification(self) -> None:
        temp_dir = make_test_dir("loop_patch")
        try:
            initial_step = make_step(1, "write_file", "Initial file")
            patch_step = make_step(2, "write_file", "Patch file")
            planner = StubPlanner(plan=[initial_step], patch_plan=[patch_step, make_step(3, "verify", "Verify patch")])
            executor = StubExecutor(
                results=[
                    {**initial_step, "status": "done", "output": "created"},
                    {**patch_step, "status": "done", "output": "patched"},
                    {**make_step(3, "verify", "Verify patch"), "status": "done", "output": "verified"},
                ]
            )
            verifier = StubVerifier(
                results=[
                    {"success": False, "summary": "missing piece", "issues": ["Need patch"]},
                    {"success": True, "summary": "done after patch", "issues": []},
                ]
            )

            state = run(
                task="finish a project after verification finds a gap",
                workspace_dir=str(temp_dir),
                max_retries=2,
                planner=planner,
                executor=executor,
                verifier=verifier,
            )

            self.assertEqual(state.status, "done")
            self.assertEqual(planner.patch_requested_with, ["Need patch"])
            self.assertEqual([step["id"] for step in state.plan], [1, 2, 3])
        finally:
            cleanup_test_dir(temp_dir)

    def test_run_stops_when_cancelled(self) -> None:
        temp_dir = make_test_dir("loop_cancel")
        try:
            planner = StubPlanner(plan=[make_step(1, "write_file", "Create file"), make_step(2, "write_file", "Another file")])
            executor = StubExecutor(results=[{**make_step(1, "write_file", "Create file"), "status": "done", "output": "created"}])
            verifier = StubVerifier(results=[])
            cancel_states = iter([False, True])

            state = run(
                task="create files but cancel after the first step completes",
                workspace_dir=str(temp_dir),
                planner=planner,
                executor=executor,
                verifier=verifier,
                should_cancel=lambda: next(cancel_states),
            )

            self.assertEqual(state.status, "cancelled")
            self.assertEqual(state.current_step_index, 1)
        finally:
            cleanup_test_dir(temp_dir)


if __name__ == "__main__":
    unittest.main()
