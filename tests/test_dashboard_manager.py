from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from daemon.dashboard.manager import DashboardRunManager
from tests._helpers import cleanup_test_dir, make_test_dir


class FakeProcess:
    def __init__(self, pid: int = 1234) -> None:
        self.pid = pid
        self._poll = None
        self.terminated = False

    def poll(self):
        return self._poll

    def terminate(self) -> None:
        self.terminated = True
        self._poll = 0

    def wait(self, timeout: int | None = None) -> int:
        self._poll = 0
        return 0

    def kill(self) -> None:
        self._poll = 0


class DashboardManagerTests(unittest.TestCase):
    def test_truncates_large_file_preview_and_marks_binary_files(self) -> None:
        temp_dir = make_test_dir("dashboard_manager_preview")
        try:
            root = Path(temp_dir)
            manager = DashboardRunManager(root)
            project = root / "demo"
            project.mkdir()
            text_file = project / "large.txt"
            text_file.write_text("a" * (manager.max_preview_bytes + 50), encoding="utf-8")
            binary_file = project / "blob.bin"
            binary_file.write_bytes(b"\x00\x10\x20\x30")

            truncated = manager.read_project_file("demo", "large.txt")
            full = manager.read_project_file("demo", "large.txt", full=True)
            binary = manager.read_project_file("demo", "blob.bin")

            self.assertTrue(truncated["truncated"])
            self.assertFalse(full["truncated"])
            self.assertTrue(binary["binary"])
        finally:
            cleanup_test_dir(temp_dir)

    def test_launch_stop_and_restart_project(self) -> None:
        temp_dir = make_test_dir("dashboard_manager_launch")
        try:
            root = Path(temp_dir)
            manager = DashboardRunManager(root)
            project = root / "demo"
            project.mkdir()
            (project / "app.py").write_text("app = object()", encoding="utf-8")

            fake_processes = [FakeProcess(pid=1111), FakeProcess(pid=2222)]

            with patch("daemon.dashboard.manager.subprocess.Popen", side_effect=fake_processes):
                launch = manager.launch_project("demo")
                self.assertEqual(launch["pid"], 1111)
                launches = manager.list_launches()
                self.assertEqual(len(launches), 1)
                self.assertTrue(launches[0]["running"])

                stopped = manager.stop_launch("demo")
                self.assertEqual(stopped["status"], "stopped")

                restarted = manager.restart_launch("demo")
                self.assertEqual(restarted["pid"], 2222)
        finally:
            cleanup_test_dir(temp_dir)


if __name__ == "__main__":
    unittest.main()
