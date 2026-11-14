from __future__ import annotations

import os
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from daemon.config import PROJECT_ROOT, WORKSPACE_DIR
from daemon.core.errors import DaemonError
from daemon.dashboard.manager import DashboardRunManager
from daemon.dashboard.schemas import (
    MIN_TASK_WORDS,
    FilePreviewView,
    HealthView,
    LaunchLogView,
    LaunchView,
    ProjectFileView,
    ProjectView,
    RunEvent,
    RunRequest,
    RunView,
    SessionLogView,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
REPO_ROOT = PROJECT_ROOT
LANDING_PAGE = REPO_ROOT / "landing" / "index.html"
DASHBOARD_PAGE = STATIC_DIR / "index.html"
NOT_FOUND_PAGE = STATIC_DIR / "404.html"
FAVICON_PATH = STATIC_DIR / "favicon.svg"

DEFAULT_ALLOWED_HOSTS = ("127.0.0.1", "localhost")
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
NO_STORE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
}
DASHBOARD_CSP_DIRECTIVES = (
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data:",
    "connect-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
)
DASHBOARD_CSP = "; ".join(DASHBOARD_CSP_DIRECTIVES)

# Module-level manager: routes look it up at call time so tests can patch it.
manager = DashboardRunManager(workspace_root=Path(WORKSPACE_DIR))


def _allowed_hosts_from_env() -> list[str]:
    configured = os.getenv("DAEMON_ALLOWED_HOSTS", "")
    extra = [host.strip() for host in configured.split(",") if host.strip()]
    return [*DEFAULT_ALLOWED_HOSTS, *extra]


def _page(path: Path, *, csp: str | None = None) -> FileResponse:
    headers = {**NO_STORE_HEADERS}
    if csp:
        headers["Content-Security-Policy"] = csp
    return FileResponse(path, headers=headers)


def create_dashboard_app(allowed_hosts: Sequence[str] | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        manager.shutdown()

    app = FastAPI(title="Daemon Dashboard", lifespan=lifespan)
    # Rejects requests whose Host header is not local, which blocks DNS-rebinding
    # pages from reading the API through an attacker-controlled hostname.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(allowed_hosts or _allowed_hosts_from_env()))
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.middleware("http")
    async def same_origin_and_headers(request: Request, call_next):
        # State-changing API calls must come from the dashboard itself. Browsers always
        # send Origin on cross-site POSTs, so a foreign Origin means another website is
        # trying to drive the local agent (CSRF). Non-browser clients send no Origin.
        if request.method not in SAFE_METHODS and request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            expected = f"{request.url.scheme}://{request.headers.get('host', '')}"
            fetch_site = request.headers.get("sec-fetch-site")
            if (origin and origin != expected) or fetch_site == "cross-site":
                return JSONResponse(status_code=403, content={"detail": "Cross-origin requests are not allowed."})

        response: Response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if request.url.path.startswith("/static/"):
            # Revalidate every load so ES module imports never run stale code.
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.exception_handler(DaemonError)
    async def daemon_error_handler(_: Request, exc: DaemonError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        if not request.url.path.startswith("/api/") and exc.status_code == 404:
            return FileResponse(NOT_FOUND_PAGE, status_code=404)
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)

    # ------------------------------------------------------------- pages

    @app.get("/", include_in_schema=False)
    def landing_home() -> FileResponse:
        return _page(LANDING_PAGE)

    @app.get("/dashboard", include_in_schema=False)
    def dashboard_home() -> FileResponse:
        return _page(DASHBOARD_PAGE, csp=DASHBOARD_CSP)

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> FileResponse:
        return FileResponse(FAVICON_PATH, media_type="image/svg+xml")

    # --------------------------------------------------------------- api

    @app.get("/api/health", response_model=HealthView)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/runs", response_model=list[RunView])
    def list_runs() -> list[dict]:
        return manager.list_runs()

    @app.post("/api/runs", response_model=RunView)
    def start_run(payload: RunRequest) -> dict:
        if payload.task_word_count < MIN_TASK_WORDS:
            raise HTTPException(status_code=422, detail=f"Task must contain at least {MIN_TASK_WORDS} words.")
        return manager.start_run(
            task=payload.task,
            workspace_dir=payload.workspace_dir or WORKSPACE_DIR,
            max_retries=payload.max_retries,
            dry_run=payload.dry_run,
        )

    @app.get("/api/runs/{run_id}", response_model=RunView)
    def get_run(run_id: str) -> dict:
        return manager.get_run(run_id)

    @app.get("/api/runs/{run_id}/events", response_model=list[RunEvent])
    def get_run_events(run_id: str) -> list[dict]:
        return manager.get_run_events(run_id)

    @app.post("/api/runs/{run_id}/cancel", response_model=RunView)
    def cancel_run(run_id: str) -> dict:
        return manager.cancel_run(run_id)

    @app.post("/api/runs/{run_id}/clone", response_model=RunView)
    def clone_run(run_id: str) -> dict:
        return manager.clone_run(run_id)

    @app.get("/api/runs/{run_id}/session-log", response_model=SessionLogView)
    def session_log(run_id: str) -> dict:
        return manager.get_session_log(run_id)

    @app.get("/api/projects", response_model=list[ProjectView])
    def list_projects(workspace_dir: str | None = None) -> list[dict]:
        return manager.list_projects(workspace_dir=workspace_dir)

    @app.get("/api/projects/{project_name}/files", response_model=list[ProjectFileView])
    def project_files(project_name: str, workspace_dir: str | None = None) -> list[dict]:
        return manager.project_files(project_name=project_name, workspace_dir=workspace_dir)

    @app.get("/api/projects/{project_name}/file", response_model=FilePreviewView)
    def project_file(
        project_name: str,
        path: str = Query(..., max_length=1_024),
        workspace_dir: str | None = None,
        full: bool = False,
    ) -> dict:
        return manager.read_project_file(
            project_name=project_name,
            relative_path=path,
            workspace_dir=workspace_dir,
            full=full,
        )

    @app.post("/api/projects/{project_name}/launch", response_model=LaunchView, response_model_exclude_unset=True)
    def launch_project(project_name: str, workspace_dir: str | None = None) -> dict:
        return manager.launch_project(project_name=project_name, workspace_dir=workspace_dir)

    @app.get("/api/projects/{project_name}/launch", response_model=LaunchView, response_model_exclude_unset=True)
    def launch_status(project_name: str) -> dict:
        launch = manager.get_launch(project_name)
        if launch is None or not launch.get("running", False):
            raise HTTPException(status_code=404, detail="Project is not running")
        return launch

    @app.get("/api/projects/{project_name}/launch/log", response_model=LaunchLogView)
    def launch_log(project_name: str) -> dict:
        return manager.read_launch_log(project_name)

    @app.get("/api/launches", response_model=list[LaunchView], response_model_exclude_unset=True)
    def list_launches() -> list[dict]:
        return manager.list_launches()

    @app.post("/api/projects/{project_name}/stop", response_model=LaunchView, response_model_exclude_unset=True)
    def stop_project(project_name: str) -> dict:
        return manager.stop_launch(project_name)

    @app.post("/api/projects/{project_name}/restart", response_model=LaunchView, response_model_exclude_unset=True)
    def restart_project(project_name: str, workspace_dir: str | None = None) -> dict:
        return manager.restart_launch(project_name, workspace_dir=workspace_dir)

    return app


app = create_dashboard_app()
