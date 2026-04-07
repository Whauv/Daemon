from __future__ import annotations

import json
import unittest
from pathlib import Path

from agents.verifier import Verifier
from core.state import AgentState
from tests._helpers import cleanup_test_dir, make_test_dir


class VerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.verifier = Verifier()

    def test_verify_fastapi_workspace(self) -> None:
        temp_dir = make_test_dir("verifier_fastapi")
        try:
            app_path = Path(temp_dir) / "app.py"
            app_path.write_text(
                "\n".join(
                    [
                        "from fastapi import FastAPI",
                        "from sqlalchemy import create_engine",
                        "app = FastAPI()",
                        "engine = create_engine('sqlite:///app.db')",
                        "@app.get('/users/')",
                        "def list_users(): return []",
                        "@app.post('/users/')",
                        "def create_user(): return {}",
                        "@app.put('/users/{user_id}')",
                        "def update_user(user_id: int): return {}",
                        "@app.delete('/users/{user_id}')",
                        "def delete_user(user_id: int): return {}",
                    ]
                ),
                encoding="utf-8",
            )
            state = AgentState(task="create a FastAPI CRUD API with 4 endpoints and SQLite", workspace_dir=str(temp_dir))

            result = self.verifier.verify_task(state)

            self.assertTrue(result["success"], result)
        finally:
            cleanup_test_dir(temp_dir)

    def test_verify_react_workspace(self) -> None:
        temp_dir = make_test_dir("verifier_react")
        try:
            root = Path(temp_dir)
            (root / "src").mkdir()
            (root / "package.json").write_text(
                json.dumps(
                    {
                        "name": "demo",
                        "scripts": {"build": "vite build"},
                    }
                ),
                encoding="utf-8",
            )
            (root / "src" / "App.jsx").write_text("export default function App() { return <div>Hello</div>; }", encoding="utf-8")
            (root / "src" / "main.jsx").write_text("import App from './App.jsx';", encoding="utf-8")
            state = AgentState(task="build a React todo app with filters and responsive layout", workspace_dir=str(temp_dir))

            result = self.verifier.verify_task(state)

            self.assertTrue(result["success"], result)
        finally:
            cleanup_test_dir(temp_dir)

    def test_verify_generic_workspace(self) -> None:
        temp_dir = make_test_dir("verifier_generic")
        try:
            root = Path(temp_dir)
            (root / "notes.md").write_text("# Notes", encoding="utf-8")
            state = AgentState(
                task="scaffold a markdown notes utility with export support",
                workspace_dir=str(temp_dir),
                completed_steps=[{"id": 1, "title": "Create notes file", "type": "write_file", "output": "done"}],
            )

            result = self.verifier.verify_task(state)

            self.assertTrue(result["success"], result)
        finally:
            cleanup_test_dir(temp_dir)


if __name__ == "__main__":
    unittest.main()
