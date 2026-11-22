from __future__ import annotations

import unittest
from unittest.mock import patch

from daemon.core import groq_client
from daemon.core.groq_client import (
    GroqClientManager,
    RequestRateLimiter,
    _status_code_from_error,
    extract_json,
)


class _FakeStatusError(Exception):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def model_dump(self) -> dict:
        return self._payload


class _FakeCompletions:
    def __init__(self, behaviors: list) -> None:
        self._behaviors = behaviors
        self.calls = 0

    def create(self, **_kwargs):
        behavior = self._behaviors[self.calls]
        self.calls += 1
        if isinstance(behavior, Exception):
            raise behavior
        return behavior


class _FakeClient:
    def __init__(self, behaviors: list) -> None:
        self.chat = type("Chat", (), {"completions": _FakeCompletions(behaviors)})()


class RateLimiterTests(unittest.TestCase):
    def test_zero_limit_never_blocks_or_records(self) -> None:
        limiter = RequestRateLimiter(max_requests=0)
        limiter.acquire()
        self.assertEqual(len(limiter._calls), 0)

    def test_records_calls_within_window(self) -> None:
        limiter = RequestRateLimiter(max_requests=5, window=60.0)
        for _ in range(3):
            limiter.acquire()
        self.assertEqual(len(limiter._calls), 3)


class ErrorClassificationTests(unittest.TestCase):
    def test_status_code_from_direct_attribute(self) -> None:
        self.assertEqual(_status_code_from_error(_FakeStatusError("x", 429)), 429)

    def test_status_code_from_response_attribute(self) -> None:
        error = Exception("boom")
        error.response = type("R", (), {"status_code": 503})()
        self.assertEqual(_status_code_from_error(error), 503)

    def test_status_code_absent(self) -> None:
        self.assertIsNone(_status_code_from_error(Exception("plain")))

    def test_rate_limit_detection(self) -> None:
        self.assertTrue(GroqClientManager._is_rate_limit_error(_FakeStatusError("x", 429)))
        self.assertTrue(GroqClientManager._is_rate_limit_error(Exception("got 429 too many")))
        self.assertFalse(GroqClientManager._is_rate_limit_error(Exception("timeout")))


class ExtractJsonTests(unittest.TestCase):
    def test_plain_and_fenced_json(self) -> None:
        self.assertEqual(extract_json('{"a": 1}'), {"a": 1})
        self.assertEqual(extract_json('```json\n{"b": 2}\n```'), {"b": 2})


class CallLlmRetryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = GroqClientManager()
        self.manager.rate_limiter = RequestRateLimiter(max_requests=0)

    def test_retries_on_rate_limit_then_succeeds(self) -> None:
        payload = {"choices": [{"message": {"content": "ok"}}]}
        self.manager.client = _FakeClient(
            [_FakeStatusError("rate", 429), _FakeStatusError("rate", 429), _FakeResponse(payload)]
        )
        with (
            patch.object(groq_client, "MAX_RETRIES", 3),
            patch.object(groq_client.time, "sleep"),
        ):
            result = self.manager.call_llm(messages=[{"role": "user", "content": "hi"}], system_prompt="s")

        self.assertEqual(result, payload)
        self.assertEqual(self.manager.client.chat.completions.calls, 3)

    def test_non_rate_limit_error_is_not_retried(self) -> None:
        self.manager.client = _FakeClient([Exception("auth failed"), Exception("should not run")])
        with patch.object(groq_client, "MAX_RETRIES", 3):
            with self.assertRaises(RuntimeError):
                self.manager.call_llm(messages=[{"role": "user", "content": "hi"}], system_prompt="s")

        self.assertEqual(self.manager.client.chat.completions.calls, 1)

    def test_missing_client_raises(self) -> None:
        self.manager.client = None
        with self.assertRaises(RuntimeError):
            self.manager.call_llm(messages=[], system_prompt="s")


if __name__ == "__main__":
    unittest.main()
