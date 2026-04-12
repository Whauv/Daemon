from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from daemon.config import WORKSPACE_DIR
from daemon.dashboard.manager import DashboardRunManager


STATIC_DIR = Path(__file__).resolve().parent / "static"
manager = DashboardRunManager(workspace_root=Path(WORKSPACE_DIR))


class RunRequest(BaseModel):
    task: str = Field(min_length=5)
    workspace_dir: str | None = None
    max_retries: int = 3
    dry_run: bool = False

    @property
    def task_word_count(self) -> int:
        return len([part for part in self.task.split() if part.strip()])


def create_dashboard_app() -> FastAPI:
    app = FastAPI(title="Daemon Dashboard")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def dashboard_home() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/runs")
    def list_runs() -> list[dict]:
        return manager.list_runs()

    @app.post("/api/runs")
    def start_run(payload: RunRequest) -> dict:
        if payload.task_word_count < 5:
            raise HTTPException(status_code=422, detail="Task must contain at least 5 words.")
        workspace_dir = payload.workspace_dir or WORKSPACE_DIR
        try:
            return manager.start_run(
                task=payload.task,
                workspace_dir=workspace_dir,
                max_retries=payload.max_retries,
                dry_run=payload.dry_run,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict:
        try:
            return manager.get_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc

    @app.get("/api/runs/{run_id}/events")
    def get_run_events(run_id: str) -> list[dict]:
        try:
            return manager.get_run_events(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc

    @app.post("/api/runs/{run_id}/cancel")
    def cancel_run(run_id: str) -> dict:
        try:
            return manager.cancel_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc

    @app.get("/api/projects")
    def list_projects(workspace_dir: str | None = None) -> list[dict]:
        try:
            return manager.list_projects(workspace_dir=workspace_dir)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/projects/{project_name}/files")
    def project_files(project_name: str, workspace_dir: str | None = None) -> list[dict]:
        try:
            return manager.project_files(project_name=project_name, workspace_dir=workspace_dir)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/projects/{project_name}/file")
    def project_file(project_name: str, path: str = Query(...), workspace_dir: str | None = None) -> dict:
        try:
            return manager.read_project_file(project_name=project_name, relative_path=path, workspace_dir=workspace_dir)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/projects/{project_name}/launch")
    def launch_project(project_name: str, workspace_dir: str | None = None) -> dict:
        try:
            return manager.launch_project(project_name=project_name, workspace_dir=workspace_dir)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/projects/{project_name}/launch")
    def launch_status(project_name: str) -> dict:
        launch = manager.get_launch(project_name)
        if launch is None:
            raise HTTPException(status_code=404, detail="Project is not running")
        return launch

    return app


app = create_dashboard_app()
