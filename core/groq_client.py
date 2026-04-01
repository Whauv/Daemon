from __future__ import annotations

import json
import threading
import time
from typing import Any

from rich.console import Console

from config import GROQ_API_KEY, MAX_RETRIES, MODEL_NAME, REQUEST_TIMEOUT


console = Console(stderr=True)


def _status_code_from_error(error: Exception) -> int | None:
    status_code = getattr(error, "status_code", None)
    if isinstance(status_code, int):
        return status_code

    response = getattr(error, "response", None)
    response_status = getattr(response, "status_code", None)
    if isinstance(response_status, int):
        return response_status

    return None


class GroqClientManager:
    _instance: "GroqClientManager | None" = None
    _instance_lock = threading.Lock()
    _model_name = MODEL_NAME

    def __new__(cls) -> "GroqClientManager":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        try:
            from groq import Groq
        except Exception:
            Groq = None
        self.client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY and Groq is not None else None

    def call_llm(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
        temperature: float = 0.2,
        json_output: bool = False,
    ) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("GROQ_API_KEY is not configured.")

        full_messages = [{"role": "system", "content": system_prompt}, *messages]
        estimated_tokens = self._estimate_tokens(full_messages)
        if estimated_tokens > 4000:
            console.print(
                f"[bold yellow]Warning:[/bold yellow] estimated request size is about {estimated_tokens} tokens."
            )

        request_kwargs: dict[str, Any] = {
            "model": self._model_name,
            "messages": full_messages,
            "temperature": temperature,
            "timeout": REQUEST_TIMEOUT,
        }
        if json_output:
            request_kwargs["response_format"] = {"type": "json_object"}

        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.chat.completions.create(**request_kwargs)
                return response.model_dump()
            except Exception as exc:
                last_error = exc
                if not self._is_rate_limit_error(exc) or attempt >= MAX_RETRIES - 1:
                    break
                sleep_for = 2**attempt
                console.print(
                    f"[yellow]Rate limit hit (429). Retrying in {sleep_for} second(s)...[/yellow]"
                )
                time.sleep(sleep_for)

        raise RuntimeError(f"Groq request failed: {last_error}") from last_error

    def complete_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
    ) -> str:
        payload = self.call_llm(
            messages=[{"role": "user", "content": user_prompt}],
            system_prompt=system_prompt,
            temperature=temperature,
        )
        return payload["choices"][0]["message"]["content"]

    def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        payload = self.call_llm(
            messages=[{"role": "user", "content": user_prompt}],
            system_prompt=system_prompt,
            temperature=temperature,
            json_output=True,
        )
        content = payload["choices"][0]["message"]["content"]
        return self._extract_json(content)

    @staticmethod
    def _estimate_tokens(messages: list[dict[str, str]]) -> int:
        total_chars = sum(len(message.get("content", "")) for message in messages)
        return max(1, total_chars // 4)

    @staticmethod
    def _is_rate_limit_error(error: Exception) -> bool:
        if _status_code_from_error(error) == 429:
            return True
        return "429" in str(error)

    @staticmethod
    def _extract_json(content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3:
                text = "\n".join(lines[1:-1]).strip()
        return json.loads(text)


def call_llm(
    messages: list[dict[str, str]],
    system_prompt: str,
    temperature: float = 0.2,
    json_output: bool = False,
) -> dict[str, Any]:
    return GroqClientManager().call_llm(
        messages=messages,
        system_prompt=system_prompt,
        temperature=temperature,
        json_output=json_output,
    )


def get_groq_client() -> GroqClientManager:
    return GroqClientManager()
