"""Pure helpers that rewrite planner-generated paths and shell commands for the
Windows workspace layout.

Extracted from ``planner.Planner`` so the (brittle, rule-heavy) normalization
logic can evolve and be tested on its own. ``Planner`` keeps thin static
delegators that call these functions.
"""

from __future__ import annotations

from typing import Any


def infer_project_dir(steps: list[dict[str, Any]]) -> str:
    for step in steps:
        if step.get("type") == "create_dir":
            path = str(step.get("args", {}).get("path", "")).strip()
            if path:
                return path
    for step in steps:
        if step.get("type") == "write_file":
            path = str(step.get("args", {}).get("path", "")).replace("/", "\\")
            if "\\" in path:
                return path.split("\\", 1)[0]
    return "project"


def relativize_path(path: str, project_dir: str) -> str:
    normalized = path.replace("/", "\\")
    workspace_marker = "\\workspace\\"
    if workspace_marker in normalized.lower():
        lowered = normalized.lower()
        index = lowered.index(workspace_marker) + len(workspace_marker)
        return normalized[index:]
    return normalized


def is_activation_command(command: str) -> bool:
    lowered = command.lower().strip()
    return lowered.endswith(("\\scripts\\activate", "\\scripts\\activate.ps1"))


def normalize_command(command: str, project_dir: str) -> str:
    normalized = command.replace("/", "\\").strip()
    lowered = normalized.lower()

    if "create-react-app" in lowered:
        return f"npm create vite@latest {project_dir} -- --template react"

    if lowered == "npm install":
        return f"cmd /c \"cd {project_dir} && npm install\""

    if lowered.startswith("npm install "):
        package_part = normalized[len("npm install") :].strip()
        return f"cmd /c \"cd {project_dir} && npm install {package_part}\""

    if lowered.startswith(("npm run dev", "npm start")):
        return f"cmd /c \"cd {project_dir} && npm run build\""

    if lowered.startswith("npm run build"):
        return f"cmd /c \"cd {project_dir} && npm run build\""

    if lowered.startswith("pip install"):
        package_part = normalized[len("pip install") :].strip()
        return f"{project_dir}\\venv\\Scripts\\python.exe -m pip install {package_part}"

    if "uvicorn main:app" in lowered:
        return normalized.replace("uvicorn main:app", f"{project_dir}\\venv\\Scripts\\python.exe -m uvicorn app:app")

    return normalized


def normalize_verify_command(command: str, project_dir: str) -> str:
    normalized = command.replace("/", "\\").strip()
    lowered = normalized.lower()
    if "npm" in lowered:
        return f"cmd /c \"cd {project_dir} && npm run build\""
    if "uvicorn" in lowered or "curl" in lowered:
        # A server process would block the run, so verify by importing the app
        # instead. The check must stay generic: it cannot know which routes the
        # task asked for (the task-level verifier handles endpoint counts).
        return (
            f"{project_dir}\\venv\\Scripts\\python.exe -c "
            "\"import pathlib, sys; "
            f"sys.path.insert(0, str(pathlib.Path(r'{project_dir}').resolve())); "
            "from app import app; "
            "routes = [route.path for route in app.routes if hasattr(route, 'path')]; "
            "assert routes, 'app has no routes'; "
            "print('verify ok')\""
        )
    return normalized
