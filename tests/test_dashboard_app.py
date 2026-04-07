from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from dashboard.app import create_dashboard_app
from dashboard.manager import DashboardRunManager
from tests._helpers import cleanup_test_dir, make_test_dir


class DashboardAppTests(unittest.TestCase):
    def test_rejects_short_tasks(self) -> None:
        temp_dir = make_test_dir("dashboard_short_task")
        try:
            manager = DashboardRunManager(Path(temp_dir))
            app = create_dashboard_app()
            with patch("dashboard.app.manager", manager):
                client = TestClient(app)
                response = client.post("/api/runs", json={"task": "too short", "workspace_dir": "demo"})

            self.assertEqual(response.status_code, 422)
        finally:
            cleanup_test_dir(temp_dir)

    def test_rejects_workspace_outside_root(self) -> None:
        temp_dir = make_test_dir("dashboard_root")
        other_dir = make_test_dir("dashboard_outside")
        try:
            manager = DashboardRunManager(Path(temp_dir))
            app = create_dashboard_app()
            with patch("dashboard.app.manager", manager):
                client = TestClient(app)
                response = client.post(
                    "/api/runs",
                    json={
                        "task": "build a React todo app with filters and responsive layout",
                        "workspace_dir": str(other_dir),
                        "dry_run": True,
                    },
                )

            self.assertEqual(response.status_code, 400)
        finally:
            cleanup_test_dir(temp_dir)
            cleanup_test_dir(other_dir)

    def test_rejects_project_file_traversal(self) -> None:
        temp_dir = make_test_dir("dashboard_traversal")
        try:
            root = Path(temp_dir)
            project = root / "demo-app"
            project.mkdir()
            (project / "app.py").write_text("print('hi')", encoding="utf-8")
            app = create_dashboard_app()
            manager = DashboardRunManager(root)
            with patch("dashboard.app.manager", manager):
                client = TestClient(app)
                response = client.get("/api/projects/demo-app/file", params={"path": "../secrets.txt"})

            self.assertEqual(response.status_code, 400)
        finally:
            cleanup_test_dir(temp_dir)


if __name__ == "__main__":
    unittest.main()
