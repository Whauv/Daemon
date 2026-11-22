from __future__ import annotations

import unittest
from pathlib import Path

from daemon.core.errors import InvalidRequestError
from daemon.core.workspace import (
    is_ignored_path,
    iter_project_files,
    list_visible_project_directories,
    resolve_dashboard_workspace,
    resolve_project_directory,
)
from tests._helpers import cleanup_test_dir, make_test_dir


class ResolveWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = make_test_dir("ws_root")

    def tearDown(self) -> None:
        cleanup_test_dir(self.root)

    def test_blank_request_returns_root(self) -> None:
        resolved = resolve_dashboard_workspace(None, self.root)
        self.assertEqual(resolved, Path(self.root).resolve())

    def test_relative_request_is_anchored_to_root(self) -> None:
        resolved = resolve_dashboard_workspace("demo", self.root)
        self.assertEqual(resolved, (Path(self.root).resolve() / "demo"))
        self.assertTrue(resolved.is_dir())

    def test_absolute_request_outside_root_is_rejected(self) -> None:
        other = make_test_dir("ws_outside")
        try:
            with self.assertRaises(InvalidRequestError):
                resolve_dashboard_workspace(str(other), self.root)
        finally:
            cleanup_test_dir(other)


class ResolveProjectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = make_test_dir("proj_root")

    def tearDown(self) -> None:
        cleanup_test_dir(self.root)

    def test_project_directory_is_under_workspace(self) -> None:
        project = resolve_project_directory("api", workspace_dir=self.root, workspace_root=self.root)
        self.assertEqual(project, (Path(self.root).resolve() / "api"))

    def test_empty_project_name_is_rejected(self) -> None:
        with self.assertRaises(InvalidRequestError):
            resolve_project_directory("", workspace_dir=self.root, workspace_root=self.root)


class ListVisibleProjectsTests(unittest.TestCase):
    def test_hidden_ignored_dirs_and_files_are_skipped(self) -> None:
        root = make_test_dir("visible_projects")
        try:
            base = Path(root)
            for name in ("beta", "alpha", ".hidden", "node_modules", ".venv"):
                (base / name).mkdir()
            (base / "not_a_dir.txt").write_text("x", encoding="utf-8")

            names = [entry.name for entry in list_visible_project_directories(root)]

            self.assertEqual(names, ["alpha", "beta"])
        finally:
            cleanup_test_dir(root)


class IterProjectFilesTests(unittest.TestCase):
    def test_ignored_paths_are_detected_and_excluded(self) -> None:
        root = make_test_dir("iter_files")
        try:
            base = Path(root)
            (base / "src").mkdir()
            (base / "src" / "main.py").write_text("x", encoding="utf-8")
            (base / "__pycache__").mkdir()
            (base / "__pycache__" / "junk.pyc").write_text("x", encoding="utf-8")

            found = {path.name for path in iter_project_files(base)}

            self.assertIn("main.py", found)
            self.assertNotIn("junk.pyc", found)
            self.assertTrue(is_ignored_path(Path("__pycache__/junk.pyc")))
            self.assertFalse(is_ignored_path(Path("src/main.py")))
        finally:
            cleanup_test_dir(root)


if __name__ == "__main__":
    unittest.main()
