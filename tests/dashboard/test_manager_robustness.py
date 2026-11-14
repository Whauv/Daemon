from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from daemon.dashboard.manager import DashboardRunManager
from tests._helpers import cleanup_test_dir, make_test_dir


class ExitedProcess:
    def __init__(self, pid: int = 4321, code: int | None = None) -> None:
        self.pid = pid
        self.code = code
        self.terminated = False

    def poll(self):
        return self.code

    def terminate(self) -> None:
        self.terminated = True
        self.code = 0

    def wait(self, timeout: float | None = None) -> int:
        return self.code or 0

    def kill(self) -> None:
        self.code = -9


class ManagerRobustnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = make_test_dir("manager_robustness")
        self.root = Path(self.temp_dir)
        self.manager = DashboardRunManager(self.root)
        (self.root / "demo").mkdir()
        (self.root / "demo" / "app.py").write_text("app = object()", encoding="utf-8")

    def tearDown(self) -> None:
        cleanup_test_dir(self.temp_dir)

    def test_non_ascii_utf8_text_is_not_binary(self) -> None:
        (self.root / "demo" / "unicode.py").write_text("# café ✓ 日本\nprint('ok')\n", encoding="utf-8")

        preview = self.manager.read_project_file("demo", "unicode.py")

        self.assertFalse(preview["binary"])
        self.assertIn("café ✓ 日本", preview["content"])

    def test_preview_truncation_does_not_split_characters(self) -> None:
        self.manager.max_preview_bytes = 5
        (self.root / "demo" / "multi.txt").write_text("ééééé", encoding="utf-8")

        preview = self.manager.read_project_file("demo", "multi.txt")

        self.assertTrue(preview["truncated"])
        self.assertEqual(preview["content"], "éé")

    def test_session_log_paths_are_unique_per_run(self) -> None:
        first = self.manager.session_log_path_for("run-a", self.root)
        second = self.manager.session_log_path_for("run-b", self.root)

        self.assertNotEqual(first, second)
        first.relative_to(self.root.resolve())

    def test_launch_records_log_and_reports_crashed_process(self) -> None:
        process = ExitedProcess(pid=77)
        with patch("daemon.dashboard.manager.subprocess.Popen", return_value=process) as popen:
            launch = self.manager.launch_project("demo")

        log_path = Path(launch["log_path"])
        log_path.relative_to(self.root.resolve())
        self.assertNotIn("DEVNULL", repr(popen.call_args))

        process.code = 1
        status = self.manager.list_launches()[0]
        self.assertFalse(status["running"])
        self.assertEqual(status["exit_code"], 1)

    def test_read_launch_log_tail(self) -> None:
        with patch("daemon.dashboard.manager.subprocess.Popen", return_value=ExitedProcess()):
            launch = self.manager.launch_project("demo")
        Path(launch["log_path"]).write_text("line1\nModuleNotFoundError: x\n", encoding="utf-8")

        log = self.manager.read_launch_log("demo")

        self.assertIn("ModuleNotFoundError", log["content"])

    def test_shutdown_terminates_running_launches(self) -> None:
        process = ExitedProcess()
        with patch("daemon.dashboard.manager.subprocess.Popen", return_value=process):
            self.manager.launch_project("demo")

        self.manager.shutdown()

        self.assertTrue(process.terminated)


if __name__ == "__main__":
    unittest.main()
