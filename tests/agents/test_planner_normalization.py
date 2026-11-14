from __future__ import annotations

import unittest

from daemon.agents.planner import Planner
from daemon.agents.verifier import Verifier
from daemon.core.groq_client import extract_json


class PlannerNormalizationTests(unittest.TestCase):
    def test_server_verify_command_is_not_tied_to_a_users_route(self) -> None:
        command = Planner._normalize_verify_command("uvicorn app:app --port 8000", "inventory")

        self.assertNotIn("/users/", command)
        self.assertIn("from app import app", command)
        self.assertIn("inventory", command)

    def test_plain_verify_command_is_preserved(self) -> None:
        self.assertEqual(Planner._normalize_verify_command("python -m pytest", "proj"), "python -m pytest")

    def test_activation_commands_are_dropped(self) -> None:
        self.assertTrue(Planner._is_activation_command("proj\\venv\\Scripts\\activate"))
        self.assertFalse(Planner._is_activation_command("proj\\venv\\Scripts\\python.exe -m pip list"))


class JsonExtractionTests(unittest.TestCase):
    def test_extracts_fenced_json(self) -> None:
        self.assertEqual(extract_json('```json\n{"a": 1}\n```'), {"a": 1})

    def test_verifier_and_client_share_extraction(self) -> None:
        payload = '{"command": "echo ok"}'
        self.assertEqual(Verifier.extract_json(payload), extract_json(payload))


if __name__ == "__main__":
    unittest.main()
