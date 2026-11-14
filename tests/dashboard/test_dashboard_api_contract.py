from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from daemon.dashboard.app import create_dashboard_app
from daemon.dashboard.manager import DashboardRunManager
from tests._helpers import cleanup_test_dir, make_client, make_test_dir

LEGACY_RUN_KEYS = {
    "id",
    "task",
    "workspace_dir",
    "max_retries",
    "dry_run",
    "status",
    "plan",
    "state",
    "session_log_path",
    "created_at",
    "updated_at",
    "error",
    "cancel_requested",
}
VALID_TASK = "build a React todo app with filters and responsive layout"


class DashboardApiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = make_test_dir("dashboard_contract")
        self.manager = DashboardRunManager(Path(self.temp_dir))
        self.patcher = patch("daemon.dashboard.app.manager", self.manager)
        self.patcher.start()
        # Keep dry runs from calling the LLM.
        self.plan_patcher = patch(
            "daemon.dashboard.manager.generate_plan_snapshot",
            return_value=[{"id": 1, "title": "verify", "type": "verify", "status": "pending"}],
        )
        self.plan_patcher.start()
        self.client = make_client(create_dashboard_app())

    def tearDown(self) -> None:
        self.plan_patcher.stop()
        self.patcher.stop()
        cleanup_test_dir(self.temp_dir)

    def test_health_contract_unchanged(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_run_response_keeps_legacy_fields(self) -> None:
        response = self.client.post("/api/runs", json={"task": VALID_TASK, "workspace_dir": "demo", "dry_run": True})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(LEGACY_RUN_KEYS.issubset(response.json().keys()))
        listed = self.client.get("/api/runs").json()
        self.assertTrue(LEGACY_RUN_KEYS.issubset(listed[0].keys()))

    def test_max_retries_is_bounded(self) -> None:
        for value in (0, 11):
            response = self.client.post(
                "/api/runs",
                json={"task": VALID_TASK, "workspace_dir": "demo", "dry_run": True, "max_retries": value},
            )
            self.assertEqual(response.status_code, 422, value)

    def test_unknown_run_returns_json_404(self) -> None:
        for path in ("/api/runs/missing", "/api/runs/missing/events", "/api/runs/missing/session-log"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 404, path)
            self.assertEqual(response.json(), {"detail": "Run not found"})

    def test_cross_origin_post_is_rejected(self) -> None:
        response = self.client.post(
            "/api/projects/demo/launch",
            headers={"Origin": "https://attacker.example"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("detail", response.json())

    def test_same_origin_post_is_allowed(self) -> None:
        response = self.client.post("/api/runs/missing/cancel", headers={"Origin": "http://127.0.0.1"})
        self.assertEqual(response.status_code, 404)

    def test_untrusted_host_header_is_rejected(self) -> None:
        rebinding_client = TestClient(create_dashboard_app(), base_url="http://attacker.example")
        self.assertEqual(rebinding_client.get("/api/health").status_code, 400)

    def test_launch_log_for_unknown_project_is_404(self) -> None:
        response = self.client.get("/api/projects/demo/launch/log")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
