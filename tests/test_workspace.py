from __future__ import annotations

import unittest
from pathlib import Path

from daemon.core.workspace import list_visible_project_directories, resolve_dashboard_workspace, resolve_project_directory
from tests._helpers import cleanup_test_dir, make_test_dir


class WorkspacePolicyTests(unittest.TestCase):
    def test_resolve_dashboard_workspace_keeps_requests_inside_root(self) -> None:
        temp_dir = make_test_dir("workspace_policy")
        try:
            root = Path(temp_dir) / "workspace"
            safe = resolve_dashboard_workspace("project-a", root)

            self.assertEqual(safe, (root / "project-a").resolve())
            self.assertTrue(safe.exists())
        finally:
            cleanup_test_dir(temp_dir)

    def test_resolve_dashboard_workspace_rejects_escape(self) -> None:
        temp_dir = make_test_dir("workspace_escape")
        try:
            root = Path(temp_dir) / "workspace"
            outside = Path(temp_dir) / "outside"
            outside.mkdir()

            with self.assertRaises(ValueError):
                resolve_dashboard_workspace(str(outside), root)
        finally:
            cleanup_test_dir(temp_dir)

    def test_resolve_project_directory_rejects_traversal(self) -> None:
        temp_dir = make_test_dir("workspace_project")
        try:
            root = Path(temp_dir) / "workspace"
            root.mkdir()

            with self.assertRaises(ValueError):
                resolve_project_directory("../escape", workspace_dir=root, workspace_root=root)
        finally:
            cleanup_test_dir(temp_dir)

    def test_list_visible_project_directories_filters_runtime_folders(self) -> None:
        temp_dir = make_test_dir("workspace_list")
        try:
            root = Path(temp_dir) / "workspace"
            (root / "demo-app").mkdir(parents=True)
            (root / "__pycache__").mkdir()
            (root / ".venv").mkdir()
            (root / "node_modules").mkdir()

            projects = list_visible_project_directories(root)

            self.assertEqual([path.name for path in projects], ["demo-app"])
        finally:
            cleanup_test_dir(temp_dir)


if __name__ == "__main__":
    unittest.main()
