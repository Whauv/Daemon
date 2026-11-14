# dashboard

The local FastAPI dashboard: HTTP API, run/launch management, and frontend assets.

- `app.py` — routes, page serving, Host/Origin protection, security headers, and the single
  `DaemonError` → JSON error mapping (`{"detail": "..."}`). Routes read the module-level
  `manager`, so tests can patch it.
- `schemas.py` — request validation (`RunRequest`) and response models. Response models allow
  extra keys so additive fields are never dropped.
- `manager.py` — `DashboardRunManager`: in-memory run registry (worker threads), file previews,
  and uvicorn launches with per-project log files under `<workspace>/.daemon/launches/`.
- `static/` — the dashboard UI (no build step). See `static/README.md`.
