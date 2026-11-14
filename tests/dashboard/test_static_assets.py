from __future__ import annotations

import re
import unittest
from html.parser import HTMLParser

from daemon.dashboard.app import STATIC_DIR, create_dashboard_app
from tests._helpers import make_client

IMPORT_PATTERN = re.compile(r"""^\s*import\s+(?:[^'"]+\s+from\s+)?["'](\.{1,2}/[^"']+)["']""", re.MULTILINE)


class _AssetCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.scripts: list[dict[str, str | None]] = []
        self.stylesheets: list[str] = []
        self.ids: list[str] = []
        self.inline_handlers: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if "id" in attributes and attributes["id"]:
            self.ids.append(attributes["id"])
        self.inline_handlers.extend(name for name in attributes if name.startswith("on"))
        if tag == "script":
            self.scripts.append(attributes)
        if tag == "link" and attributes.get("rel") == "stylesheet":
            self.stylesheets.append(attributes.get("href") or "")


class StaticAssetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = make_client(create_dashboard_app())
        self.collector = _AssetCollector()
        self.collector.feed((STATIC_DIR / "index.html").read_text(encoding="utf-8"))

    def test_dashboard_has_no_inline_script_or_handlers(self) -> None:
        # The dashboard CSP is script-src 'self'; inline code would be blocked.
        for script in self.collector.scripts:
            self.assertTrue(script.get("src"), "inline <script> found in dashboard HTML")
        self.assertEqual(self.collector.inline_handlers, [])

    def test_dashboard_ids_are_unique(self) -> None:
        duplicates = {item for item in self.collector.ids if self.collector.ids.count(item) > 1}
        self.assertEqual(duplicates, set())

    def test_referenced_local_assets_are_served(self) -> None:
        local = [s["src"] for s in self.collector.scripts] + self.collector.stylesheets
        for href in [item for item in local if item and item.startswith("/static/")]:
            response = self.client.get(href)
            self.assertEqual(response.status_code, 200, href)
            self.assertEqual(response.headers.get("cache-control"), "no-cache", href)

    def test_every_module_import_resolves(self) -> None:
        modules = list((STATIC_DIR / "js").rglob("*.js"))
        self.assertTrue(modules)
        for module in modules:
            for specifier in IMPORT_PATTERN.findall(module.read_text(encoding="utf-8")):
                target = (module.parent / specifier).resolve()
                self.assertTrue(target.is_file(), f"{module.name} imports missing {specifier}")

    def test_dashboard_page_sends_csp_and_security_headers(self) -> None:
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn("script-src 'self'", response.headers["content-security-policy"])
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-frame-options"], "DENY")

    def test_dashboard_no_longer_shows_intro_overlay(self) -> None:
        self.assertNotIn("intro-overlay", self.collector.ids)


if __name__ == "__main__":
    unittest.main()
