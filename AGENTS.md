# AGENTS.md

## Purpose

This repository contains Daemon, a local AI agent orchestrator with a CLI and dashboard.

## Setup Commands

```bash
pip install -r requirements.txt
python main.py --help
python main.py --dashboard
```

## Test Commands

```bash
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Folder Map

- `src/daemon/agents`: planning, execution, and verification agents
- `src/daemon/core`: orchestration loop, state, Groq client, workspace policy
- `src/daemon/dashboard`: FastAPI dashboard API and frontend assets
- `src/daemon/tools`: file and shell utility layer
- `src/daemon/ui`: Rich CLI display
- `tests`: regression and placeholder test coverage

## Code Style

- Preserve business logic during refactors
- Keep all generated files inside the configured workspace
- Prefer explicit imports from the `daemon` package
- Add tests for contract-sensitive behavior before broad refactors
