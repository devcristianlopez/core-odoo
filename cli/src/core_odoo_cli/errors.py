"""CLI error type."""

from __future__ import annotations


class CliError(Exception):
    """A recoverable CLI failure with a localized message."""

    def __init__(self, message: str, *, code: str = "error", exit_code: int = 1) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.exit_code = exit_code
