from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4


TEST_ROOT = Path(__file__).resolve().parents[1] / ".test_tmp"
TEST_ROOT.mkdir(parents=True, exist_ok=True)


def make_test_dir(prefix: str) -> Path:
    target = TEST_ROOT / f"{prefix}_{uuid4().hex}"
    target.mkdir(parents=True, exist_ok=True)
    return target


def cleanup_test_dir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
