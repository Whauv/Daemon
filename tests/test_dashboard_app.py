from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from daemon.dashboard.app import create_dashboard_app
from daemon.dashboard.manager import DashboardRunManager
from tests._helpers import cleanup_test_dir, make_test_dir


class DashboardAppTests(unittest.TestCase):
    def test_serves_landing_and_dashboard_pages(self) -> None:
        app = create_dashboard_app()
        client = TestClient(app)

        landing = client.get("/")
        dashboard = client.get("/dashboard")
        missing = client.get("/missing-page")
        favicon = client.get("/favicon.ico")

        self.assertEqual(landing.status_code, 200)
        self.assertIn("Open Product", landing.text)
        self.assertIn("Local AI Agent Orchestrator", landing.text)
        self.assertIn("Daemon", landing.text)
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn("Daemon Dashboard", dashboard.text)
        self.assertEqual(missing.status_code, 404)
        self.assertIn("Page not found", missing.text)
        self.assertEqual(favicon.status_code, 200)

    def test_rejects_short_tasks(self) -> None:
        temp_dir = make_test_dir("dashboard_short_task")
        try:
            manager = DashboardRunManager(Path(temp_dir))
            app = create_dashboard_app()
            with patch("daemon.dashboard.app.manager", manager):
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
            with patch("daemon.dashboard.app.manager", manager):
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

    def test_can_clone_run_and_read_session_log(self) -> None:
        temp_dir = make_test_dir("dashboard_clone")
        try:
            root = Path(temp_dir)
            manager = DashboardRunManager(root)
            app = create_dashboard_app()
            with patch("daemon.dashboard.app.manager", manager):
                client = TestClient(app)
                response = client.post(
                    "/api/runs",
                    json={
                        "task": "build a React todo app with filters and responsive layout",
                        "workspace_dir": "demo",
                        "dry_run": True,
                    },
                )
                self.assertEqual(response.status_code, 200)
                run_id = response.json()["id"]
                manager._update_run(run_id, status="done")
                manager._action_timestamps.clear()

                cloned = client.post(f"/api/runs/{run_id}/clone")
                self.assertEqual(cloned.status_code, 200)

                session_log = root / "demo" / "daemon_session_log.json"
                session_log.write_text('{"status":"done"}', encoding="utf-8")
                manager._update_run(run_id, session_log_path=str(session_log))
                log_response = client.get(f"/api/runs/{run_id}/session-log")
                self.assertEqual(log_response.status_code, 200)
                self.assertIn("status", log_response.json()["content"])
        finally:
            cleanup_test_dir(temp_dir)

    def test_rejects_project_file_traversal(self) -> None:
        temp_dir = make_test_dir("dashboard_traversal")
        try:
            root = Path(temp_dir)
            project = root / "demo-app"
            project.mkdir()
            (project / "app.py").write_text("print('hi')", encoding="utf-8")
            app = create_dashboard_app()
            manager = DashboardRunManager(root)
            with patch("daemon.dashboard.app.manager", manager):
                client = TestClient(app)
                response = client.get("/api/projects/demo-app/file", params={"path": "../secrets.txt"})

            self.assertEqual(response.status_code, 400)
        finally:
            cleanup_test_dir(temp_dir)


if __name__ == "__main__":
    unittest.main()
