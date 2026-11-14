from __future__ import annotations

import codecs
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any
from uuid import uuid4

from daemon.config import PROJECT_ROOT
from daemon.core.errors import InvalidRequestError, NotFoundError
from daemon.core.loop import generate_plan_snapshot, run
from daemon.core.workspace import (
    DAEMON_STATE_DIRNAME,
    iter_project_files,
    list_visible_project_directories,
    resolve_dashboard_workspace,
    resolve_project_directory,
)

ACTIVE_RUN_STATUSES = frozenset({"queued", "running", "cancelling", "verifying", "executing", "planning"})
TERMINAL_RUN_STATUSES = frozenset({"done", "failed", "cancelled"})
MAX_EVENTS_PER_RUN = 200
BINARY_SNIFF_BYTES = 8192
LAUNCH_LOG_TAIL_BYTES = 20_000


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_not_found() -> NotFoundError:
    return NotFoundError("Run not found")


class DashboardRunManager:
    """In-memory registry of dashboard runs and launched project servers.

    All mutable state is guarded by ``self._lock``. Long-running work (agent runs,
    process start/stop) happens outside the lock.
    """

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve()
        self._lock = threading.Lock()
        self._runs: dict[str, dict[str, Any]] = {}
        self._launches: dict[str, dict[str, Any]] = {}
        self._launch_processes: dict[str, subprocess.Popen[Any]] = {}
        self._launch_logs: dict[str, IO[bytes]] = {}
        self._action_timestamps: dict[str, float] = {}
        self.max_concurrent_runs = 2
        self.max_preview_bytes = 100_000
        self.max_full_preview_bytes = 1_000_000

    # ------------------------------------------------------------------ runs

    def start_run(
        self,
        *,
        task: str,
        workspace_dir: str,
        max_retries: int,
        dry_run: bool,
    ) -> dict[str, Any]:
        self._guard_action("start_run")
        run_id = uuid4().hex
        workspace = resolve_dashboard_workspace(workspace_dir, self.workspace_root)
        now = _utc_now()
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
            "created_at": now,
            "updated_at": now,
            "error": None,
            "cancel_requested": False,
        }
        with self._lock:
            # Capacity check and insert happen atomically so two quick requests
            # cannot both slip past the limit.
            self._check_run_capacity_locked(task=task, workspace_dir=str(workspace))
            self._runs[run_id] = record

        worker = threading.Thread(
            target=self._run_worker,
            kwargs={
                "run_id": run_id,
                "task": task,
                "workspace_dir": str(workspace),
                "max_retries": max_retries,
                "dry_run": dry_run,
            },
            daemon=True,
            name=f"daemon-run-{run_id[:8]}",
        )
        worker.start()
        return self.get_run(run_id)

    def session_log_path_for(self, run_id: str, workspace: Path) -> Path:
        return (workspace / DAEMON_STATE_DIRNAME / "runs" / f"{run_id}.json").resolve()

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

            session_log_path = self.session_log_path_for(run_id, Path(workspace_dir))
            final_state = run(
                task=task,
                workspace_dir=workspace_dir,
                max_retries=max_retries,
                display=None,
                event_handler=lambda event: self._handle_loop_event(run_id, event),
                should_cancel=lambda: self._is_cancel_requested(run_id),
                session_log_path=session_log_path,
            )
            status = final_state.status if final_state.status in TERMINAL_RUN_STATUSES else "failed"
            self._update_run(
                run_id,
                status=status,
                state=final_state.model_dump(),
                plan=final_state.plan,
                session_log_path=str(session_log_path),
            )
        except Exception as exc:
            self._update_run(run_id, status="failed", error=str(exc))
            self._append_event(run_id, {"type": "fatal", "message": str(exc)})

    def _handle_loop_event(self, run_id: str, event: dict[str, Any]) -> None:
        updates: dict[str, Any] = {}
        if "plan" in event:
            updates["plan"] = event["plan"]
        if "state" in event:
            updates["state"] = event["state"]
        event_type = event.get("type")
        if event_type == "success":
            updates["status"] = "done"
        elif event_type in {"fatal", "failed"}:
            updates["status"] = "failed"
        elif event_type == "cancelled":
            updates["status"] = "cancelled"
        self._update_run(run_id, **updates)
        self._append_event(run_id, event)

    def _append_event(self, run_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            record = self._runs[run_id]
            record["events"].append({"timestamp": _utc_now(), **event})
            del record["events"][:-MAX_EVENTS_PER_RUN]
            record["updated_at"] = _utc_now()

    def _update_run(self, run_id: str, **updates: Any) -> None:
        with self._lock:
            self._runs[run_id].update(updates)
            self._runs[run_id]["updated_at"] = _utc_now()

    def list_runs(self) -> list[dict[str, Any]]:
        with self._lock:
            runs = [self._public_run_view(record) for record in self._runs.values()]
        return sorted(runs, key=lambda item: item["created_at"], reverse=True)

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                raise _run_not_found()
            return self._public_run_view(record)

    def get_run_events(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                raise _run_not_found()
            return list(record["events"])

    def cancel_run(self, run_id: str) -> dict[str, Any]:
        self._guard_action("cancel_run", min_interval=0.25)
        with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                raise _run_not_found()
            if record["status"] in TERMINAL_RUN_STATUSES:
                raise InvalidRequestError(f"Run has already finished with status '{record['status']}'.")
            record["cancel_requested"] = True
            record["status"] = "cancelling"
            record["updated_at"] = _utc_now()
        self._append_event(run_id, {"type": "status", "message": "Cancellation requested."})
        return self.get_run(run_id)

    def clone_run(self, run_id: str) -> dict[str, Any]:
        source = self.get_run(run_id)
        return self.start_run(
            task=source["task"],
            workspace_dir=source["workspace_dir"],
            max_retries=source["max_retries"],
            dry_run=source["dry_run"],
        )

    def get_session_log(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                raise _run_not_found()
            session_log_path = record.get("session_log_path")
        if not session_log_path:
            raise InvalidRequestError("Session log is not available for this run yet.")
        target = Path(session_log_path).resolve()
        if not target.is_file():
            raise InvalidRequestError("Session log file could not be found.")
        return {
            "path": str(target),
            "content": target.read_text(encoding="utf-8", errors="ignore"),
        }

    # -------------------------------------------------------------- projects

    def list_projects(self, workspace_dir: str | None = None) -> list[dict[str, Any]]:
        root = resolve_dashboard_workspace(workspace_dir, self.workspace_root)
        projects = [
            {
                "name": entry.name,
                "path": str(entry.resolve()),
                "has_app": (entry / "app.py").exists() or (entry / "main.py").exists(),
                "requirements": (entry / "requirements.txt").exists(),
            }
            for entry in list_visible_project_directories(root)
        ]
        return sorted(projects, key=lambda item: item["name"])

    def project_files(self, project_name: str, workspace_dir: str | None = None) -> list[dict[str, Any]]:
        project_root = self._project_root(project_name, workspace_dir)
        files = [
            {"path": path.relative_to(project_root).as_posix(), "size": path.stat().st_size}
            for path in iter_project_files(project_root)
        ]
        return sorted(files, key=lambda item: item["path"])

    def read_project_file(
        self,
        project_name: str,
        relative_path: str,
        workspace_dir: str | None = None,
        *,
        full: bool = False,
    ) -> dict[str, Any]:
        project_root = self._project_root(project_name, workspace_dir)
        target = (project_root / relative_path).resolve()
        try:
            display_path = target.relative_to(project_root).as_posix()
        except ValueError as exc:
            raise InvalidRequestError("Requested file escapes the selected project.") from exc
        if not target.is_file():
            raise InvalidRequestError("Requested file does not exist.")

        size = target.stat().st_size
        byte_limit = self.max_full_preview_bytes if full else self.max_preview_bytes
        with target.open("rb") as handle:
            data = handle.read(byte_limit + 1)
        exceeds_limit = len(data) > byte_limit
        data = data[:byte_limit]

        if self._looks_binary(data):
            return {
                "path": display_path,
                "content": "",
                "truncated": False,
                "binary": True,
                "size": size,
                "message": "Binary files cannot be previewed in the dashboard.",
            }

        # errors="ignore" drops a multi-byte character split by the byte limit.
        content = data.decode("utf-8", errors="ignore")
        if exceeds_limit and not full:
            message = "Preview truncated. Load full file to inspect the rest."
        elif exceeds_limit:
            message = f"File is larger than {self.max_full_preview_bytes:,} bytes; showing the beginning only."
        else:
            message = ""
        return {
            "path": display_path,
            "content": content,
            "truncated": exceeds_limit and not full,
            "binary": False,
            "size": size,
            "message": message,
        }

    def _project_root(self, project_name: str, workspace_dir: str | None) -> Path:
        return resolve_project_directory(
            project_name,
            workspace_dir=workspace_dir or self.workspace_root,
            workspace_root=self.workspace_root,
        )

    # -------------------------------------------------------------- launches

    def launch_project(
        self,
        project_name: str,
        workspace_dir: str | None = None,
        *,
        skip_guard: bool = False,
    ) -> dict[str, Any]:
        if not skip_guard:
            self._guard_action("launch_project", min_interval=0.5)
        project_root = self._project_root(project_name, workspace_dir)
        if (project_root / "app.py").exists():
            app_target = "app:app"
        elif (project_root / "main.py").exists():
            app_target = "main:app"
        else:
            raise InvalidRequestError("Project does not contain a launchable FastAPI entrypoint.")

        with self._lock:
            process = self._launch_processes.get(project_name)
            existing = self._launches.get(project_name)
            if existing is not None and process is not None and process.poll() is None:
                return self._launch_view_locked(project_name)

        port = self._next_free_port()
        log_path = self._launch_log_path(project_name)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = log_path.open("wb")
        command = [
            str(self._python_executable()),
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
        try:
            process = subprocess.Popen(
                command,
                cwd=str(project_root),
                stdout=log_handle,
                stderr=subprocess.STDOUT,
            )
        except Exception:
            log_handle.close()
            raise

        record = {
            "project_name": project_name,
            "pid": process.pid,
            "port": port,
            "url": f"http://127.0.0.1:{port}",
            "docs_url": f"http://127.0.0.1:{port}/docs",
            "started_at": _utc_now(),
            "log_path": str(log_path),
        }
        with self._lock:
            self._close_log_locked(project_name)
            self._launches[project_name] = record
            self._launch_processes[project_name] = process
            self._launch_logs[project_name] = log_handle
            return self._launch_view_locked(project_name)

    def stop_launch(self, project_name: str, *, skip_guard: bool = False) -> dict[str, Any]:
        if not skip_guard:
            self._guard_action("stop_launch", min_interval=0.25)
        with self._lock:
            process = self._launch_processes.get(project_name)
            launch = self._launches.get(project_name)
        if process is None or launch is None or process.poll() is not None:
            raise InvalidRequestError("Project is not currently running.")

        self._terminate(process)
        with self._lock:
            self._close_log_locked(project_name)
            self._launches[project_name] = {**launch, "status": "stopped", "stopped_at": _utc_now()}
            return dict(self._launches[project_name])

    def restart_launch(self, project_name: str, workspace_dir: str | None = None) -> dict[str, Any]:
        try:
            self.stop_launch(project_name, skip_guard=True)
        except InvalidRequestError:
            pass
        return self.launch_project(project_name, workspace_dir=workspace_dir, skip_guard=True)

    def list_launches(self) -> list[dict[str, Any]]:
        with self._lock:
            launches = [self._launch_view_locked(name) for name in self._launches]
        return sorted(launches, key=lambda item: item["project_name"].lower())

    def get_launch(self, project_name: str) -> dict[str, Any] | None:
        with self._lock:
            if project_name not in self._launches:
                return None
            return self._launch_view_locked(project_name)

    def read_launch_log(self, project_name: str) -> dict[str, Any]:
        with self._lock:
            launch = self._launches.get(project_name)
        if launch is None or not launch.get("log_path"):
            raise NotFoundError("Project has not been launched")
        log_path = Path(launch["log_path"])
        if not log_path.is_file():
            return {"path": str(log_path), "content": "", "truncated": False}
        size = log_path.stat().st_size
        with log_path.open("rb") as handle:
            handle.seek(max(0, size - LAUNCH_LOG_TAIL_BYTES))
            data = handle.read()
        return {
            "path": str(log_path),
            "content": data.decode("utf-8", errors="replace"),
            "truncated": size > LAUNCH_LOG_TAIL_BYTES,
        }

    def shutdown(self) -> None:
        """Stop every launched project server. Called when the dashboard exits."""
        with self._lock:
            processes = list(self._launch_processes.items())
        for name, process in processes:
            if process.poll() is None:
                try:
                    self._terminate(process)
                except Exception:
                    pass
            with self._lock:
                self._close_log_locked(name)

    def _launch_view_locked(self, project_name: str) -> dict[str, Any]:
        launch = self._launches[project_name]
        process = self._launch_processes.get(project_name)
        exit_code = process.poll() if process is not None else None
        return {**launch, "running": process is not None and exit_code is None, "exit_code": exit_code}

    def _launch_log_path(self, project_name: str) -> Path:
        safe_name = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in project_name)
        return self.workspace_root / DAEMON_STATE_DIRNAME / "launches" / f"{safe_name}.log"

    def _close_log_locked(self, project_name: str) -> None:
        handle = self._launch_logs.pop(project_name, None)
        if handle is not None:
            handle.close()

    @staticmethod
    def _terminate(process: subprocess.Popen[Any]) -> None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    # ---------------------------------------------------------------- guards

    def _guard_action(self, action: str, *, min_interval: float = 0.5) -> None:
        with self._lock:
            now = time.monotonic()
            last = self._action_timestamps.get(action, 0.0)
            if now - last < min_interval:
                raise InvalidRequestError("Please wait a moment before repeating that action.")
            self._action_timestamps[action] = now

    def _check_run_capacity_locked(self, *, task: str, workspace_dir: str) -> None:
        active_runs = [record for record in self._runs.values() if record["status"] in ACTIVE_RUN_STATUSES]
        if len(active_runs) >= self.max_concurrent_runs:
            raise InvalidRequestError("Too many active runs. Wait for one to finish before starting another.")
        if any(record["task"] == task and record["workspace_dir"] == workspace_dir for record in active_runs):
            raise InvalidRequestError("A run for this task and workspace is already active.")

    def _is_cancel_requested(self, run_id: str) -> bool:
        with self._lock:
            record = self._runs.get(run_id)
            return bool(record and record.get("cancel_requested"))

    # --------------------------------------------------------------- helpers

    @staticmethod
    def _looks_binary(data: bytes) -> bool:
        """Treat data as text when it is valid UTF-8 (including non-ASCII) without NUL bytes."""
        sample = data[:BINARY_SNIFF_BYTES]
        if b"\x00" in sample:
            return True
        decoder = codecs.getincrementaldecoder("utf-8")()
        try:
            # final=False tolerates a multi-byte character cut off by the sample boundary.
            decoder.decode(sample, final=False)
        except UnicodeDecodeError:
            return True
        return False

    @staticmethod
    def _python_executable() -> Path:
        venv_dir = PROJECT_ROOT / ".venv"
        for candidate in (venv_dir / "Scripts" / "python.exe", venv_dir / "bin" / "python"):
            if candidate.exists():
                return candidate.resolve()
        return Path(sys.executable).resolve()

    @staticmethod
    def _next_free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    @staticmethod
    def _public_run_view(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": record["id"],
            "task": record["task"],
            "workspace_dir": record["workspace_dir"],
            "max_retries": record["max_retries"],
            "dry_run": record["dry_run"],
            "status": record["status"],
            "plan": record["plan"],
            "state": record["state"],
            "session_log_path": record["session_log_path"],
            "created_at": record["created_at"],
            "updated_at": record["updated_at"],
            "error": record["error"],
            "cancel_requested": record["cancel_requested"],
        }
