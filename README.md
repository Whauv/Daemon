# Nexus Agent

Nexus Agent is a local AI agent orchestrator built from scratch in pure Python. It accepts a high-level task, asks Groq for a dependency-aware plan, executes each step inside a guarded workspace, verifies the outcome, and loops until the task is done or retry limits are reached.

## Setup

1. Create and activate a Python 3.11+ virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Add your Groq API key to `.env`:

```env
GROQ_API_KEY=your_key_here
```

## Example Commands

```bash
python main.py --task "create a python CRUD REST API using FastAPI and SQLite with 4 endpoints"
python main.py --task "build a React todo app with filters local storage and responsive layout" --workspace ./my-projects/todo
python main.py --task "scaffold a command line markdown notes app with search export and tests" --dry-run
```

## Agent Loop Phases

1. Planning
   The planner asks Groq for an ordered JSON plan with concrete steps.
2. Execution
   The executor creates directories, writes files, runs commands, and attempts command auto-fixes when needed.
3. Verification
   The verifier checks step outputs and performs a final QA-style task review.
4. Recovery
   Failed steps can be replanned, and final verification issues can generate patch plans.
5. Logging
   The full session state is saved to `nexus_session_log.json` inside the workspace.

## Folder Structure

```text
Daemon/
|-- main.py
|-- .env
|-- .gitignore
|-- README.md
|-- requirements.txt
|-- config.py
|-- agents/
|   |-- __init__.py
|   |-- planner.py
|   |-- executor.py
|   `-- verifier.py
|-- core/
|   |-- __init__.py
|   |-- groq_client.py
|   |-- loop.py
|   `-- state.py
|-- tools/
|   |-- __init__.py
|   |-- file_tools.py
|   `-- shell_tools.py
`-- ui/
    |-- __init__.py
    `-- display.py
```

## Notes

- The project uses the Groq `llama-3.3-70b-versatile` model only.
- File writes are guarded so paths cannot escape the workspace directory.
- `--dry-run` prints a generated plan without executing any steps.
- Very short tasks are rejected so the planner gets enough detail to produce a useful plan.
