from __future__ import annotations

import unittest
from pathlib import Path

from daemon.core.loop import run
from tests._helpers import cleanup_test_dir, make_test_dir
from tests.test_loop import StubExecutor, StubPlanner, StubVerifier, make_step


class SessionLogTests(unittest.TestCase):
    def test_run_specific_session_log_is_written_alongside_legacy_log(self) -> None:
        temp_dir = make_test_dir("loop_session_log")
        try:
            root = Path(temp_dir)
            run_log = root / ".daemon" / "runs" / "abc.json"
            step = make_step(1, "write_file", "Create file")
            events: list[dict] = []

            state = run(
                task="write a single file into the workspace",
                workspace_dir=str(root),
                planner=StubPlanner(plan=[step]),
                executor=StubExecutor(results=[{**step, "status": "done", "output": "ok"}]),
                verifier=StubVerifier(results=[{"success": True, "summary": "ok", "issues": []}]),
                event_handler=events.append,
                session_log_path=run_log,
            )

            self.assertEqual(state.status, "done")
            self.assertTrue(run_log.exists())
            self.assertTrue((root / "daemon_session_log.json").exists())
            saved = [event for event in events if event["type"] == "session_saved"]
            self.assertEqual(saved[-1]["path"], str(run_log.resolve()))
        finally:
            cleanup_test_dir(temp_dir)


if __name__ == "__main__":
    unittest.main()
