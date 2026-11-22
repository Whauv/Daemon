from __future__ import annotations

import codecs
import logging
import socket
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
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

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _run_not_found() -> NotFoundError:
    return NotFoundError("Run not found")


class _RunRegistry:
    """In-memory registry of agent runs. All state is guarded by its own lock."""

    def __init__(self, *, max_concurrent_runs: int) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, dict[str, Any]] = {}
        self.max_concurrent_runs = max_concurrent_runs

    def add(self, record: dict[str, Any]) -> None:
        # Capacity check and insert happen atomically so two quick requests
        # cannot both slip past the limit.
        with self._lock:
            self._check_capacity_locked(task=record["task"], workspace_dir=record["workspace_dir"])
            self._runs[record["id"]] = record

    def update(self, run_id: str, **updates: Any) -> None:
        with self._lock:
            self._runs[run_id].update(updates)
            self._runs[run_id]["updated_at"] = _utc_now()

    def append_event(self, run_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            record = self._runs[run_id]
            record["events"].append({"timestamp": _utc_now(), **event})
            del record["events"][:-MAX_EVENTS_PER_RUN]
            record["updated_at"] = _utc_now()

    def list_views(self) -> list[dict[str, Any]]:
        with self._lock:
            runs = [self._public_run_view(record) for record in self._runs.values()]
        return sorted(runs, key=lambda item: item["created_at"], reverse=True)

    def get_view(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                raise _run_not_found()
            return self._public_run_view(record)

    def get_events(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                raise _run_not_found()
            return list(record["events"])

    def request_cancel(self, run_id: str) -> None:
        with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                raise _run_not_found()
            if record["status"] in TERMINAL_RUN_STATUSES:
                raise InvalidRequestError(f"Run has already finished with status '{record['status']}'.")
            record["cancel_requested"] = True
            record["status"] = "cancelling"
            record["updated_at"] = _utc_now()

    def is_cancel_requested(self, run_id: str) -> bool:
        with self._lock:
            record = self._runs.get(run_id)
            return bool(record and record.get("cancel_requested"))

    def require_session_log_path(self, run_id: str) -> str | None:
        with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                raise _run_not_found()
            return record.get("session_log_path")

    def _check_capacity_locked(self, *, task: str, workspace_dir: str) -> None:
        active_runs = [record for record in self._runs.values() if record["status"] in ACTIVE_RUN_STATUSES]
        if len(active_runs) >= self.max_concurrent_runs:
            raise InvalidRequestError("Too many active runs. Wait for one to finish before starting another.")
        if any(record["task"] == task and record["workspace_dir"] == workspace_dir for record in active_runs):
            raise InvalidRequestError("A run for this task and workspace is already active.")

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


class _LaunchSupervisor:
    """Owns the launched project server processes and their log handles."""

    def __init__(self, *, workspace_root: Path) -> None:
        self.workspace_root = workspace_root
        self._lock = threading.Lock()
        self._launches: dict[str, dict[str, Any]] = {}
        self._processes: dict[str, subprocess.Popen[Any]] = {}
        self._logs: dict[str, IO[bytes]] = {}

    def launch(self, *, project_name: str, project_root: Path, app_target: str) -> dict[str, Any]:
        with self._lock:
            process = self._processes.get(project_name)
            existing = self._launches.get(project_name)
            if existing is not None and process is not None and process.poll() is None:
                return self._view_locked(project_name)

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
            self._processes[project_name] = process
            self._logs[project_name] = log_handle
            return self._view_locked(project_name)

    def stop(self, project_name: str) -> dict[str, Any]:
        with self._lock:
            process = self._processes.get(project_name)
            launch = self._launches.get(project_name)
        if process is None or launch is None or process.poll() is not None:
            raise InvalidRequestError("Project is not currently running.")

        self._terminate(process)
        with self._lock:
            self._close_log_locked(project_name)
            self._launches[project_name] = {**launch, "status": "stopped", "stopped_at": _utc_now()}
            return dict(self._launches[project_name])

    def list_views(self) -> list[dict[str, Any]]:
        with self._lock:
            launches = [self._view_locked(name) for name in self._launches]
        return sorted(launches, key=lambda item: item["project_name"].lower())

    def get_view(self, project_name: str) -> dict[str, Any] | None:
        with self._lock:
            if project_name not in self._launches:
                return None
            return self._view_locked(project_name)

    def read_log(self, project_name: str) -> dict[str, Any]:
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
            processes = list(self._processes.items())
        for name, process in processes:
            if process.poll() is None:
                try:
                    self._terminate(process)
                except (OSError, subprocess.SubprocessError):
                    # Keep stopping the remaining servers; this one may already have exited.
                    logger.warning("Could not stop launched project %s (pid %s)", name, process.pid, exc_info=True)
            with self._lock:
                self._close_log_locked(name)

    def _view_locked(self, project_name: str) -> dict[str, Any]:
        launch = self._launches[project_name]
        process = self._processes.get(project_name)
        exit_code = process.poll() if process is not None else None
        return {**launch, "running": process is not None and exit_code is None, "exit_code": exit_code}

    def _launch_log_path(self, project_name: str) -> Path:
        safe_name = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in project_name)
        return self.workspace_root / DAEMON_STATE_DIRNAME / "launches" / f"{safe_name}.log"

    def _close_log_locked(self, project_name: str) -> None:
        handle = self._logs.pop(project_name, None)
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


class _ProjectFiles:
    """Stateless reader for project listings and file previews."""

    @staticmethod
    def list_projects(root: Path) -> list[dict[str, Any]]:
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

    @staticmethod
    def project_files(project_root: Path) -> list[dict[str, Any]]:
        files = [
            {"path": path.relative_to(project_root).as_posix(), "size": path.stat().st_size}
            for path in iter_project_files(project_root)
        ]
        return sorted(files, key=lambda item: item["path"])

    @classmethod
    def read_file(
        cls,
        project_root: Path,
        relative_path: str,
        *,
        max_preview_bytes: int,
        max_full_preview_bytes: int,
        full: bool,
    ) -> dict[str, Any]:
        target = (project_root / relative_path).resolve()
        try:
            display_path = target.relative_to(project_root).as_posix()
        except ValueError as exc:
            raise InvalidRequestError("Requested file escapes the selected project.") from exc
        if not target.is_file():
            raise InvalidRequestError("Requested file does not exist.")

        size = target.stat().st_size
        byte_limit = max_full_preview_bytes if full else max_preview_bytes
        with target.open("rb") as handle:
            data = handle.read(byte_limit + 1)
        exceeds_limit = len(data) > byte_limit
        data = data[:byte_limit]

        if cls._looks_binary(data):
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
            message = f"File is larger than {max_full_preview_bytes:,} bytes; showing the beginning only."
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


class DashboardRunManager:
    """Facade over the run registry, launch supervisor, and project-file reader.

    Public methods and their JSON shapes are unchanged; this class coordinates the
    collaborators, owns per-action rate limiting, and runs the agent worker thread.
    """

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve()
        self.max_concurrent_runs = 2
        self.max_preview_bytes = 100_000
        self.max_full_preview_bytes = 1_000_000
        self._action_timestamps: dict[str, float] = {}
        self._guard_lock = threading.Lock()
        self._registry = _RunRegistry(max_concurrent_runs=self.max_concurrent_runs)
        self._launches = _LaunchSupervisor(workspace_root=self.workspace_root)

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
        self._registry.add(record)

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
                should_cancel=lambda: self._registry.is_cancel_requested(run_id),
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
        # Worker-thread boundary: any error must mark the run failed instead of leaving it stuck as "running".
        except Exception as exc:  # noqa: BLE001
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
        self._registry.append_event(run_id, event)

    def _update_run(self, run_id: str, **updates: Any) -> None:
        self._registry.update(run_id, **updates)

    def list_runs(self) -> list[dict[str, Any]]:
        return self._registry.list_views()

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self._registry.get_view(run_id)

    def get_run_events(self, run_id: str) -> list[dict[str, Any]]:
        return self._registry.get_events(run_id)

    def cancel_run(self, run_id: str) -> dict[str, Any]:
        self._guard_action("cancel_run", min_interval=0.25)
        self._registry.request_cancel(run_id)
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
        session_log_path = self._registry.require_session_log_path(run_id)
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
        return _ProjectFiles.list_projects(root)

    def project_files(self, project_name: str, workspace_dir: str | None = None) -> list[dict[str, Any]]:
        project_root = self._project_root(project_name, workspace_dir)
        return _ProjectFiles.project_files(project_root)

    def read_project_file(
        self,
        project_name: str,
        relative_path: str,
        workspace_dir: str | None = None,
        *,
        full: bool = False,
    ) -> dict[str, Any]:
        project_root = self._project_root(project_name, workspace_dir)
        return _ProjectFiles.read_file(
            project_root,
            relative_path,
            max_preview_bytes=self.max_preview_bytes,
            max_full_preview_bytes=self.max_full_preview_bytes,
            full=full,
        )

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
        return self._launches.launch(project_name=project_name, project_root=project_root, app_target=app_target)

    def stop_launch(self, project_name: str, *, skip_guard: bool = False) -> dict[str, Any]:
        if not skip_guard:
            self._guard_action("stop_launch", min_interval=0.25)
        return self._launches.stop(project_name)

    def restart_launch(self, project_name: str, workspace_dir: str | None = None) -> dict[str, Any]:
        try:
            self.stop_launch(project_name, skip_guard=True)
        except InvalidRequestError:
            pass
        return self.launch_project(project_name, workspace_dir=workspace_dir, skip_guard=True)

    def list_launches(self) -> list[dict[str, Any]]:
        return self._launches.list_views()

    def get_launch(self, project_name: str) -> dict[str, Any] | None:
        return self._launches.get_view(project_name)

    def read_launch_log(self, project_name: str) -> dict[str, Any]:
        return self._launches.read_log(project_name)

    def shutdown(self) -> None:
        self._launches.shutdown()

    # ---------------------------------------------------------------- guards

    def _guard_action(self, action: str, *, min_interval: float = 0.5) -> None:
        with self._guard_lock:
            now = time.monotonic()
            last = self._action_timestamps.get(action, 0.0)
            if now - last < min_interval:
                raise InvalidRequestError("Please wait a moment before repeating that action.")
            self._action_timestamps[action] = now
