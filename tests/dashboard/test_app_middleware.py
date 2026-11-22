from __future__ import annotations

import unittest

from daemon.dashboard.app import create_dashboard_app
from tests._helpers import make_client


class SecurityHeaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = make_client(create_dashboard_app())

    def test_api_responses_carry_security_headers(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertEqual(response.headers["referrer-policy"], "same-origin")

    def test_static_assets_are_revalidated(self) -> None:
        response = self.client.get("/static/js/main.js")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("cache-control"), "no-cache")


class SameOriginGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = make_client(create_dashboard_app())

    def test_cross_site_fetch_header_is_blocked(self) -> None:
        response = self.client.post(
            "/api/runs/missing/cancel",
            headers={"sec-fetch-site": "cross-site"},
        )
        self.assertEqual(response.status_code, 403)

    def test_foreign_origin_is_blocked(self) -> None:
        response = self.client.post(
            "/api/runs/missing/cancel",
            headers={"Origin": "https://evil.example"},
        )
        self.assertEqual(response.status_code, 403)

    def test_request_without_origin_is_allowed(self) -> None:
        # Non-browser clients send no Origin; the guard must not block them.
        response = self.client.post("/api/runs/missing/cancel")
        self.assertEqual(response.status_code, 404)

    def test_safe_methods_are_never_blocked(self) -> None:
        response = self.client.get("/api/runs", headers={"sec-fetch-site": "cross-site"})
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
