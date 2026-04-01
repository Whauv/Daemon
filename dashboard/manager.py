from __future__ import annotations

import socket
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from core.loop import generate_plan_snapshot, run
from tools.file_tools import guard_workspace_path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DashboardRunManager:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve()
        self._lock = threading.Lock()
        self._runs: dict[str, dict[str, Any]] = {}
        self._launches: dict[str, dict[str, Any]] = {}

    def start_run(
        self,
        *,
        task: str,
        workspace_dir: str,
        max_retries: int,
        dry_run: bool,
    ) -> dict[str, Any]:
        run_id = uuid4().hex
        workspace = Path(workspace_dir).resolve()
        workspace.mkdir(parents=True, exist_ok=True)

        record = {
            "id": run_id,
            "task": task,
            "workspace_dir": str(workspace),
            "max_retries": max_retries,
            "dry_run": dry_run,
            "status": "queued",
            "events": [],
            "plan": [],
            "state": None,
            "session_log_path": None,
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
            "error": None,
            "cancel_requested": False,
        }
        with self._lock:
            self._runs[run_id] = record

        worker = threading.Thread(
            target=self._run_worker,
            kwargs={"run_id": run_id, "task": task, "workspace_dir": str(workspace), "max_retries": max_retries, "dry_run": dry_run},
            daemon=True,
        )
        worker.start()
        return self.get_run(run_id)

    def _run_worker(self, *, run_id: str, task: str, workspace_dir: str, max_retries: int, dry_run: bool) -> None:
        try:
            self._append_event(run_id, {"type": "status", "message": "Starting run..."})
            self._update_run(run_id, status="running")

            if dry_run:
                plan = generate_plan_snapshot(task=task, workspace_dir=workspace_dir)
                self._update_run(run_id, status="done", plan=plan)
                self._append_event(run_id, {"type": "plan", "task": task, "plan": plan})
                self._append_event(run_id, {"type": "success", "result": {"summary": "Dry run complete."}})
                return

            final_state = run(
                task=task,
                workspace_dir=workspace_dir,
                max_retries=max_retries,
                display=None,
                event_handler=lambda event: self._handle_loop_event(run_id, event),
                should_cancel=lambda: self._is_cancel_requested(run_id),
            )
            status = final_state.status
            if status not in {"done", "failed", "cancelled"}:
                status = "failed"
            session_log_path = str((Path(workspace_dir) / "daemon_session_log.json").resolve())
            self._update_run(
                run_id,
                status=status,
                state=final_state.model_dump(),
                plan=final_state.plan,
                session_log_path=session_log_path,
            )
        except Exception as exc:
            self._update_run(run_id, status="failed", error=str(exc))
            self._append_event(run_id, {"type": "fatal", "message": str(exc)})

    def _handle_loop_event(self, run_id: str, event: dict[str, Any]) -> None:
        updates: dict[str, Any] = {"updated_at": _utc_now()}
        if "plan" in event:
            updates["plan"] = event["plan"]
        if "state" in event:
            updates["state"] = event["state"]
        if event.get("type") == "success":
            updates["status"] = "done"
        if event.get("type") in {"fatal", "failed"}:
            updates["status"] = "failed"
        if event.get("type") == "cancelled":
            updates["status"] = "cancelled"
        self._update_run(run_id, **updates)
        self._append_event(run_id, event)

    def _append_event(self, run_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            record = self._runs[run_id]
            enriched = {"timestamp": _utc_now(), **event}
            record["events"].append(enriched)
            record["events"] = record["events"][-200:]
            record["updated_at"] = _utc_now()

    def _update_run(self, run_id: str, **updates: Any) -> None:
        with self._lock:
            self._runs[run_id].update(updates)
            self._runs[run_id]["updated_at"] = _utc_now()

    def list_runs(self) -> list[dict[str, Any]]:
        with self._lock:
            return [self._public_run_view(run) for run in self._runs.values()]

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            return self._public_run_view(self._runs[run_id])

    def get_run_events(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._runs[run_id]["events"])

    def cancel_run(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            if run_id not in self._runs:
                raise KeyError(run_id)
            self._runs[run_id]["cancel_requested"] = True
            self._runs[run_id]["status"] = "cancelling"
            self._runs[run_id]["updated_at"] = _utc_now()
        self._append_event(run_id, {"type": "status", "message": "Cancellation requested."})
        return self.get_run(run_id)

    def list_projects(self, workspace_dir: str | None = None) -> list[dict[str, Any]]:
        root = Path(workspace_dir).resolve() if workspace_dir else self.workspace_root
        root.mkdir(parents=True, exist_ok=True)
        projects: list[dict[str, Any]] = []
        for entry in root.iterdir():
            if not entry.is_dir():
                continue
            app_file = entry / "app.py"
            main_file = entry / "main.py"
            requirements_file = entry / "requirements.txt"
            projects.append(
                {
                    "name": entry.name,
                    "path": str(entry.resolve()),
                    "has_app": app_file.exists() or main_file.exists(),
                    "requirements": requirements_file.exists(),
                }
            )
        return sorted(projects, key=lambda item: item["name"])

    def project_files(self, project_name: str, workspace_dir: str | None = None) -> list[dict[str, Any]]:
        root = Path(workspace_dir).resolve() if workspace_dir else self.workspace_root
        project_root = guard_workspace_path(project_name, str(root))
        files: list[dict[str, Any]] = []
        for path in project_root.rglob("*"):
            if "venv" in path.parts or "__pycache__" in path.parts:
                continue
            if path.is_file():
                files.append({"path": str(path.relative_to(project_root)).replace("\\", "/"), "size": path.stat().st_size})
        return sorted(files, key=lambda item: item["path"])

    def read_project_file(self, project_name: str, relative_path: str, workspace_dir: str | None = None) -> dict[str, Any]:
        root = Path(workspace_dir).resolve() if workspace_dir else self.workspace_root
        project_root = guard_workspace_path(project_name, str(root))
        target = guard_workspace_path(str(Path(project_name) / relative_path), str(root))
        return {
            "path": str(target.relative_to(project_root)).replace("\\", "/"),
            "content": target.read_text(encoding="utf-8", errors="ignore"),
        }

    def launch_project(self, project_name: str, workspace_dir: str | None = None) -> dict[str, Any]:
        root = Path(workspace_dir).resolve() if workspace_dir else self.workspace_root
        project_root = guard_workspace_path(project_name, str(root))
        app_target = "app:app" if (project_root / "app.py").exists() else "main:app"
        port = self._next_free_port()
        python_exe = self._python_executable()

        command = [
            str(python_exe),
            "-m",
            "uvicorn",
            app_target,
            "--app-dir",
            str(project_root),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ]
        process = subprocess.Popen(
            command,
            cwd=str(project_root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        record = {
            "project_name": project_name,
            "pid": process.pid,
            "port": port,
            "url": f"http://127.0.0.1:{port}",
            "docs_url": f"http://127.0.0.1:{port}/docs",
            "started_at": _utc_now(),
        }
        with self._lock:
            self._launches[project_name] = record
        return record

    def get_launch(self, project_name: str) -> dict[str, Any] | None:
        with self._lock:
            return self._launches.get(project_name)

    def _is_cancel_requested(self, run_id: str) -> bool:
        with self._lock:
            run = self._runs.get(run_id)
            return bool(run and run.get("cancel_requested"))

    @staticmethod
    def _python_executable() -> Path:
        local_venv = Path(".venv") / "Scripts" / "python.exe"
        if local_venv.exists():
            return local_venv.resolve()
        return Path(sys.executable).resolve()

    @staticmethod
    def _next_free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    @staticmethod
    def _public_run_view(run: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": run["id"],
            "task": run["task"],
            "workspace_dir": run["workspace_dir"],
            "max_retries": run["max_retries"],
            "dry_run": run["dry_run"],
            "status": run["status"],
            "plan": run["plan"],
            "state": run["state"],
            "session_log_path": run["session_log_path"],
            "created_at": run["created_at"],
            "updated_at": run["updated_at"],
            "error": run["error"],
            "cancel_requested": run["cancel_requested"],
        }
