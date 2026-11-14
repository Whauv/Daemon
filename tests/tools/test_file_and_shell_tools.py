from __future__ import annotations

import sys
import unittest
from pathlib import Path

from daemon.tools.file_tools import guard_workspace_path, read_file, write_file
from daemon.tools.shell_tools import run_command
from tests._helpers import cleanup_test_dir, make_test_dir


class FileToolTests(unittest.TestCase):
    def test_guard_rejects_absolute_and_traversal_paths(self) -> None:
        temp_dir = make_test_dir("tools_guard")
        try:
            with self.assertRaises(ValueError):
                guard_workspace_path(str(Path(temp_dir).resolve() / "x.txt"), str(temp_dir))
            with self.assertRaises(ValueError):
                guard_workspace_path("../x.txt", str(temp_dir))
        finally:
            cleanup_test_dir(temp_dir)

    def test_write_then_read_round_trip(self) -> None:
        temp_dir = make_test_dir("tools_roundtrip")
        try:
            self.assertTrue(write_file("nested/a.txt", "héllo", str(temp_dir)))
            self.assertEqual(read_file("nested/a.txt", str(temp_dir)), "héllo")
            self.assertFalse(write_file("../escape.txt", "x", str(temp_dir)))
        finally:
            cleanup_test_dir(temp_dir)


class ShellToolTests(unittest.TestCase):
    def test_run_command_reports_exit_code(self) -> None:
        temp_dir = make_test_dir("tools_shell")
        try:
            ok = run_command(f'"{sys.executable}" -c "print(42)"', str(temp_dir))
            bad = run_command(f'"{sys.executable}" -c "raise SystemExit(3)"', str(temp_dir))

            self.assertEqual(ok["exit_code"], 0)
            self.assertEqual(ok["stdout"], "42")
            self.assertEqual(bad["exit_code"], 3)
        finally:
            cleanup_test_dir(temp_dir)


if __name__ == "__main__":
    unittest.main()
