# Daemon

Daemon is a local AI agent orchestrator built in Python. It turns a high-level task into an execution plan, runs each step inside a guarded workspace, verifies the result, and offers both a Rich CLI and a local FastAPI dashboard for monitoring runs.

## Project Layout

```text
Daemon/
├── main.py
├── src/daemon/
├── tests/
├── .github/
├── README.md
├── AGENTS.md
├── CONTRIBUTING.md
├── LICENSE
├── .env.example
└── requirements.txt
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

## Testing

```bash
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Environment Variables

See [.env.example](C:/Users/prana/OneDrive/Documents/Playground/Daemon/.env.example) for the full list of supported settings.

## Notes

- Source code now lives under `src/daemon`.
- `main.py` remains the stable entry shim for local runs.
- Local runtime data such as generated workspaces, databases, and virtual environments should stay out of version control.
