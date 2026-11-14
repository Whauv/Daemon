"""Test package bootstrap.

* Makes the ``daemon`` package importable without setting PYTHONPATH.
* Blanks the Groq API key before ``daemon.config`` loads ``.env`` so the suite
  can never make live LLM calls with a developer's real credentials.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

os.environ["GROQ_API_KEY"] = ""
