# Daemon

Daemon is a local AI agent orchestrator built in Python. It turns a high-level task into an execution plan, runs each step inside a guarded workspace, verifies the result, and offers both a Rich CLI and a local FastAPI dashboard for monitoring runs.

## Project Layout

```text
Daemon/
|-- landing/
|-- main.py
|-- src/daemon/
|-- tests/
|-- .github/
|-- README.md
|-- AGENTS.md
|-- CONTRIBUTING.md
|-- LICENSE
|-- .env.example
`-- requirements.txt
```

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and fill in your values.

## Usage

Run the CLI:

```bash
python main.py --task "create a python CRUD REST API using FastAPI and SQLite with 4 endpoints"
```

Run the dashboard:

```bash
python main.py --dashboard
```

Dry run a task:

```bash
python main.py --task "build a React todo app with filters local storage and responsive layout" --dry-run
```

## Local Routes

- Landing page: `http://127.0.0.1:8080/`
- Product dashboard: `http://127.0.0.1:8080/dashboard`

## Dashboard

- **Layout:** compose a run and browse history on the left, follow the active run's plan timeline in the centre, and use the tabbed workbench (Live log, Projects, Launches, Inspector) on the right. The layout collapses to two columns on tablets and one on phones.
- **Live updates:** the page polls the API every 1.5 s while a run is active, backs off when the backend is unreachable, and pauses while the tab is hidden. Reloading the page re-attaches to a run that is still in progress.
- **Launching projects:** "Launch app" starts a generated FastAPI project with uvicorn. Server output is written to `<workspace>/.daemon/launches/<project>.log` (viewable under Launches → View log). Crashed launches are reported, and launched servers are stopped when the dashboard shuts down.
- **Session logs:** every run writes `daemon_session_log.json` in its workspace (as before); dashboard runs also write a per-run copy to `<workspace>/.daemon/runs/<run-id>.json` so concurrent runs never overwrite each other.
- **Local-only by design:** the server binds to `127.0.0.1`, rejects requests whose `Host` header is not local, and rejects state-changing API calls from other origins. To reach it through another hostname, list it in `DAEMON_ALLOWED_HOSTS` (comma-separated).
- **Motion:** interface animations use the Web Animations API and are disabled when the OS "reduce motion" setting is on.

## Testing

```bash
.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
# or
.venv\Scripts\python.exe -m pytest -q
```

The test suite blanks `GROQ_API_KEY`, so it never makes live LLM calls.

## Environment Variables

See [.env.example](.env.example) for the full list of supported settings.

## Notes

- Source code lives under `src/daemon`.
- Configuration is read from the repository-root `.env` (environment variables take precedence). A relative `WORKSPACE_DIR` is resolved against the repository root.
- `main.py` remains the stable entry shim for local runs.
- The landing page is served from [landing/index.html](landing/index.html).
- Local runtime data such as generated workspaces, databases, and virtual environments should stay out of version control.
