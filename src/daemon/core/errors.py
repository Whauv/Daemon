"""Domain errors shared by the core and the dashboard.

They subclass the built-in exceptions the code raised before (``ValueError`` and
``KeyError``) so existing callers that catch those keep working.
"""

from __future__ import annotations


class DaemonError(Exception):
    """Base class for expected, user-facing failures."""

    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return self.message


class InvalidRequestError(DaemonError, ValueError):
    """The request is well-formed but cannot be fulfilled (bad path, wrong state, etc.)."""

    status_code = 400


class NotFoundError(DaemonError, KeyError):
    """The requested run, project, or launch does not exist."""

    status_code = 404
