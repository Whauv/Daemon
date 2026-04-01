from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field
import os


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Settings(BaseModel):
    groq_api_key: str = Field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    groq_model: str = Field(
        default_factory=lambda: os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    )
    request_timeout: int = Field(
        default_factory=lambda: int(os.getenv("REQUEST_TIMEOUT", "60"))
    )
    max_retries: int = Field(default_factory=lambda: int(os.getenv("MAX_RETRIES", "3")))
    retry_backoff_seconds: float = Field(
        default_factory=lambda: float(os.getenv("RETRY_BACKOFF_SECONDS", "2.0"))
    )
    max_requests_per_minute: int = Field(
        default_factory=lambda: int(os.getenv("MAX_REQUESTS_PER_MINUTE", "25"))
    )
    max_iterations: int = Field(
        default_factory=lambda: int(os.getenv("MAX_ITERATIONS", "12"))
    )


settings = Settings()
