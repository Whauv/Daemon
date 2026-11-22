from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from daemon.agents.executor import Executor
from daemon.core.state import AgentState
from daemon.tools.file_tools import read_file
from tests._helpers import cleanup_test_dir, make_test_dir


def _llm_reply(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


def _step(step_type: str, args: dict, **extra) -> dict:
    base = {
        "id": 1,
        "title": "step",
        "description": "a step",
        "type": step_type,
        "args": args,
        "status": "pending",
        "output": "",
    }
    base.update(extra)
    return base


class ExecutorPathNormalizationTests(unittest.TestCase):
    def test_absolute_path_inside_workspace_becomes_relative(self) -> None:
        temp_dir = make_test_dir("exec_path")
        try:
            state = AgentState(task="t", workspace_dir=str(temp_dir))
            absolute = str((Path(temp_dir) / "pkg" / "a.txt").resolve())

            result = Executor._normalize_workspace_path_arg(absolute, state)

            self.assertEqual(Path(result), Path("pkg/a.txt"))
        finally:
            cleanup_test_dir(temp_dir)

    def test_absolute_path_outside_workspace_is_left_alone(self) -> None:
        temp_dir = make_test_dir("exec_path_out")
        other = make_test_dir("exec_path_other")
        try:
            state = AgentState(task="t", workspace_dir=str(temp_dir))
            outside = str((Path(other) / "x.txt").resolve())

            self.assertEqual(Executor._normalize_workspace_path_arg(outside, state), outside)
            self.assertEqual(Executor._normalize_workspace_path_arg("", state), "")
        finally:
            cleanup_test_dir(temp_dir)
            cleanup_test_dir(other)


class ExecutorStepTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = make_test_dir("exec_steps")
        self.state = AgentState(task="build something", workspace_dir=str(self.temp_dir))
        self.executor = Executor()

    def tearDown(self) -> None:
        cleanup_test_dir(self.temp_dir)

    def test_create_dir_marks_done_and_records_completion(self) -> None:
        result = self.executor.execute_step(_step("create_dir", {"path": "pkg"}), self.state)

        self.assertEqual(result["status"], "done")
        self.assertTrue((Path(self.temp_dir) / "pkg").is_dir())
        self.assertEqual(self.state.completed_steps[-1]["status"], "done")

    def test_write_file_writes_content(self) -> None:
        result = self.executor.execute_step(
            _step("write_file", {"path": "pkg/app.py", "content": "print('hi')"}),
            self.state,
        )

        self.assertEqual(result["status"], "done")
        self.assertEqual(read_file("pkg/app.py", str(self.temp_dir)), "print('hi')")

    def test_incomplete_content_is_regenerated_via_llm(self) -> None:
        step = _step("write_file", {"path": "app.py", "content": "# TODO: implement here"})
        with patch(
            "daemon.agents.executor.call_llm",
            return_value=_llm_reply('{"content": "print(\'done\')"}'),
        ) as llm:
            result = self.executor.execute_step(step, self.state)

        llm.assert_called_once()
        self.assertEqual(result["status"], "done")
        self.assertEqual(read_file("app.py", str(self.temp_dir)), "print('done')")

    def test_regeneration_failure_keeps_original_content(self) -> None:
        step = _step("write_file", {"path": "app.py", "content": "placeholder"})
        with patch("daemon.agents.executor.call_llm", side_effect=RuntimeError("no network")):
            result = self.executor.execute_step(step, self.state)

        self.assertEqual(result["status"], "done")
        self.assertEqual(read_file("app.py", str(self.temp_dir)), "placeholder")

    def test_run_command_success(self) -> None:
        step = _step("run_command", {"command": "echo ok"})
        with patch(
            "daemon.agents.executor.run_command",
            return_value={"stdout": "ok", "stderr": "", "exit_code": 0},
        ):
            result = self.executor.execute_step(step, self.state)

        self.assertEqual(result["status"], "done")
        self.assertEqual(result["output"], "ok")

    def test_run_command_retries_with_suggested_fix(self) -> None:
        step = _step("run_command", {"command": "bad-cmd"})
        results = [
            {"stdout": "", "stderr": "not found", "exit_code": 1},
            {"stdout": "fixed", "stderr": "", "exit_code": 0},
        ]
        with (
            patch("daemon.agents.executor.run_command", side_effect=results),
            patch(
                "daemon.agents.executor.call_llm",
                return_value=_llm_reply('{"command": "good-cmd"}'),
            ),
        ):
            result = self.executor.execute_step(step, self.state)

        self.assertEqual(result["status"], "done")
        self.assertEqual(result["args"]["command"], "good-cmd")

    def test_run_command_fails_when_no_fix_available(self) -> None:
        step = _step("run_command", {"command": "bad-cmd"})
        with (
            patch(
                "daemon.agents.executor.run_command",
                return_value={"stdout": "", "stderr": "boom", "exit_code": 2},
            ),
            patch("daemon.agents.executor.call_llm", return_value=_llm_reply('{"command": ""}')),
        ):
            result = self.executor.execute_step(step, self.state)

        self.assertEqual(result["status"], "failed")
        self.assertIn("boom", result["output"])
        self.assertEqual(self.state.failed_steps[-1]["status"], "failed")

    def test_verify_step_with_command_runs_it(self) -> None:
        step = _step("verify", {"check": "imports ok", "command": "python -c 'pass'"})
        with patch(
            "daemon.agents.executor.run_command",
            return_value={"stdout": "verify ok", "stderr": "", "exit_code": 0},
        ):
            result = self.executor.execute_step(step, self.state)

        self.assertEqual(result["status"], "done")


if __name__ == "__main__":
    unittest.main()
