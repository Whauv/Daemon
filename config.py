from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:
    def load_dotenv(*args: object, **kwargs: object) -> bool:
        return False


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    def __init__(self) -> None:
        self.GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
        self.MODEL_NAME = os.getenv("MODEL_NAME", "llama-3.3-70b-versatile")
        self.MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
        self.WORKSPACE_DIR = os.getenv("WORKSPACE_DIR", str((BASE_DIR / "workspace").resolve()))
        self.REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "60"))
        self.RETRY_BACKOFF_SECONDS = float(os.getenv("RETRY_BACKOFF_SECONDS", "2.0"))
        self.MAX_REQUESTS_PER_MINUTE = int(os.getenv("MAX_REQUESTS_PER_MINUTE", "25"))


settings = Settings()

GROQ_API_KEY = settings.GROQ_API_KEY
MODEL_NAME = settings.MODEL_NAME
MAX_RETRIES = settings.MAX_RETRIES
WORKSPACE_DIR = settings.WORKSPACE_DIR
REQUEST_TIMEOUT = settings.REQUEST_TIMEOUT
