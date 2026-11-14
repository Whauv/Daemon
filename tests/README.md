# tests

Regression tests for the orchestrator, agents, tools, and dashboard. Subfolders mirror the runtime package layout (`agents`, `core`, `dashboard`, `tools`, `ui`).

`tests/__init__.py` adds `src/` to `sys.path` and blanks `GROQ_API_KEY`, so the suite runs without `PYTHONPATH` and never calls the live LLM.
