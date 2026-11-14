from __future__ import annotations

import unittest
from pathlib import Path

from daemon.agents.verifier import Verifier
from daemon.core.state import AgentState
from tests._helpers import cleanup_test_dir, make_test_dir

FASTAPI_APP = "\n".join(
    [
        "from fastapi import FastAPI",
        "app = FastAPI()",
        "@app.get('/items/')",
        "def list_items(): return []",
    ]
)


class VerifierScopeTests(unittest.TestCase):
    def test_api_keyword_matches_whole_words_only(self) -> None:
        self.assertFalse(Verifier._looks_like_fastapi_task("build a capital city quiz with rapid feedback", []))
        self.assertTrue(Verifier._looks_like_fastapi_task("build a REST API for notes", []))
        self.assertTrue(Verifier._looks_like_fastapi_task("expose two APIs for billing", []))

    def test_stale_projects_do_not_satisfy_a_new_run(self) -> None:
        temp_dir = make_test_dir("verifier_stale")
        try:
            root = Path(temp_dir)
            (root / "old_api").mkdir()
            (root / "old_api" / "app.py").write_text(FASTAPI_APP, encoding="utf-8")
            (root / "new_api").mkdir()
            (root / "new_api" / "app.py").write_text("print('not an api yet')", encoding="utf-8")
            state = AgentState(
                task="build a small FastAPI service with 1 endpoint",
                workspace_dir=str(root),
                completed_steps=[
                    {"id": 1, "title": "dir", "type": "create_dir", "args": {"path": "new_api"}, "output": ""},
                    {"id": 2, "title": "app", "type": "write_file", "args": {"path": "new_api\\app.py"}, "output": ""},
                ],
            )

            result = Verifier()._verify_task_from_workspace(state)

            self.assertFalse(result["success"], result)
        finally:
            cleanup_test_dir(temp_dir)

    def test_scope_falls_back_to_workspace_root_without_project_paths(self) -> None:
        temp_dir = make_test_dir("verifier_root_scope")
        try:
            root = Path(temp_dir)
            state = AgentState(task="anything at all here", workspace_dir=str(root))
            self.assertEqual(Verifier._verification_root(state), root)
        finally:
            cleanup_test_dir(temp_dir)


if __name__ == "__main__":
    unittest.main()
