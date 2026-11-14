from __future__ import annotations

import unittest
from pathlib import Path

from daemon import config


class ConfigTests(unittest.TestCase):
    def test_project_root_is_repository_root(self) -> None:
        self.assertTrue((config.PROJECT_ROOT / "main.py").exists())
        self.assertEqual(config.ENV_FILES[0], config.PROJECT_ROOT / ".env")

    def test_defaults_resolve_against_project_root(self) -> None:
        root = Path("/tmp/daemon-root").resolve()
        settings = config.build_settings({}, project_root=root)

        self.assertEqual(settings.WORKSPACE_DIR, str(root / "workspace"))
        self.assertEqual(settings.MAX_RETRIES, 3)
        self.assertEqual(settings.MODEL_NAME, "llama-3.3-70b-versatile")
        self.assertEqual(settings.GROQ_API_KEY, "")

    def test_relative_workspace_is_anchored_to_project_root(self) -> None:
        root = Path("/tmp/daemon-root").resolve()
        settings = config.build_settings({"WORKSPACE_DIR": "./workspace"}, project_root=root)

        self.assertEqual(settings.WORKSPACE_DIR, str(root / "workspace"))

    def test_invalid_numeric_setting_names_the_variable(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            config.build_settings({"MAX_RETRIES": "three"}, project_root=Path("."))

        self.assertIn("MAX_RETRIES", str(ctx.exception))

    def test_reads_rate_limit_settings(self) -> None:
        settings = config.build_settings(
            {"RETRY_BACKOFF_SECONDS": "0.5", "MAX_REQUESTS_PER_MINUTE": "10"},
            project_root=Path("."),
        )

        self.assertEqual(settings.RETRY_BACKOFF_SECONDS, 0.5)
        self.assertEqual(settings.MAX_REQUESTS_PER_MINUTE, 10)


if __name__ == "__main__":
    unittest.main()
