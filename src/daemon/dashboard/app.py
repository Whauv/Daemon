from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel, Field

from daemon.config import WORKSPACE_DIR
from daemon.dashboard.manager import DashboardRunManager


STATIC_DIR = Path(__file__).resolve().parent / "static"
REPO_ROOT = Path(__file__).resolve().parents[3]
LANDING_PAGE = REPO_ROOT / "landing" / "index.html"
DASHBOARD_PAGE = STATIC_DIR / "index.html"
NOT_FOUND_PAGE = STATIC_DIR / "404.html"
FAVICON_PATH = STATIC_DIR / "favicon.svg"
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

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        if request.url.path.startswith("/api/"):
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        if exc.status_code == 404:
            return FileResponse(NOT_FOUND_PAGE, status_code=404)
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.get("/")
    def landing_home() -> FileResponse:
        return FileResponse(
            LANDING_PAGE,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    @app.get("/dashboard")
    def dashboard_home() -> FileResponse:
        return FileResponse(
            DASHBOARD_PAGE,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> FileResponse:
        return FileResponse(FAVICON_PATH, media_type="image/svg+xml")

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

    @app.post("/api/runs/{run_id}/clone")
    def clone_run(run_id: str) -> dict:
        try:
            return manager.clone_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/runs/{run_id}/session-log")
    def session_log(run_id: str) -> dict:
        try:
            return manager.get_session_log(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

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
    def project_file(
        project_name: str,
        path: str = Query(...),
        workspace_dir: str | None = None,
        full: bool = False,
    ) -> dict:
        try:
            return manager.read_project_file(
                project_name=project_name,
                relative_path=path,
                workspace_dir=workspace_dir,
                full=full,
            )
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
        if launch is None or not launch.get("running", False):
            raise HTTPException(status_code=404, detail="Project is not running")
        return launch

    @app.get("/api/launches")
    def list_launches() -> list[dict]:
        return manager.list_launches()

    @app.post("/api/projects/{project_name}/stop")
    def stop_project(project_name: str) -> dict:
        try:
            return manager.stop_launch(project_name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/projects/{project_name}/restart")
    def restart_project(project_name: str, workspace_dir: str | None = None) -> dict:
        try:
            return manager.restart_launch(project_name, workspace_dir=workspace_dir)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app


app = create_dashboard_app()
