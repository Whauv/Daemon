from __future__ import annotations

import re
import subprocess


ANSI_PATTERN = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def _strip_ansi(text: str) -> str:
    return ANSI_PATTERN.sub("", text).strip()


def run_command(command: str, workspace: str, timeout: int = 30) -> dict[str, str | int]:
    try:
        completed = subprocess.run(
            command,
            cwd=workspace,
            shell=True,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        return {
            "stdout": _strip_ansi(completed.stdout),
            "stderr": _strip_ansi(completed.stderr),
            "exit_code": completed.returncode,
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return {
            "stdout": _strip_ansi(stdout),
            "stderr": _strip_ansi(stderr) or f"Command timed out after {timeout} seconds.",
            "exit_code": -1,
        }
    except Exception as exc:
        return {
            "stdout": "",
            "stderr": _strip_ansi(str(exc)),
            "exit_code": 1,
        }
