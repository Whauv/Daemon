from __future__ import annotations

import subprocess
from pathlib import Path


def run_command(cmd: str, cwd: Path | None = None) -> dict[str, str | int]:
    completed = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        shell=True,
        text=True,
        capture_output=True,
    )
    return {
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "exit_code": completed.returncode,
    }
