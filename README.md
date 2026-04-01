# Nexus Agent

Nexus Agent is a local AI agent orchestrator built in pure Python. It takes a high-level task, generates a dependency-aware plan, executes each step, verifies the result, and loops until the task is complete or retry limits are reached.

## Stack

- Python 3.11+
- `groq` using `llama-3.3-70b-versatile`
- `rich`
- `pydantic`
- `python-dotenv`

## Project Structure

```text
Daemon/
├── main.py
├── .env
├── requirements.txt
├── config.py
├── agents/
│   ├── __init__.py
│   ├── planner.py
│   ├── executor.py
│   └── verifier.py
├── core/
│   ├── __init__.py
│   ├── groq_client.py
│   ├── loop.py
│   └── state.py
├── tools/
│   ├── __init__.py
│   ├── file_tools.py
│   └── shell_tools.py
└── ui/
    ├── __init__.py
    └── display.py
```

## Features

- Groq-backed planner that returns strict JSON step plans
- Executor for directory creation, file writing, command execution, and verification steps
- Auto-fix retries for failed shell commands
- QA-style final task verification
- Rich live terminal dashboard with plan tree, status spinner, event feed, and progress bar
- Session log export to `nexus_session_log.json`

## Setup

1. Create a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Add your Groq key to `.env`:

```env
GROQ_API_KEY=your_key_here
```

## Run

```bash
python main.py "create a CRUD app"
```

Optional:

```bash
python main.py "build a CLI todo app" --workspace .
```

## Notes

- Nexus Agent is intentionally built without LangChain or LangGraph.
- File operations are restricted to the configured workspace.
- Shell commands run with timeouts and ANSI-stripped output.
- If the Groq package or API key is not available, live agent execution will not complete successfully.
