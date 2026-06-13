"""Typed exceptions and JSON error envelopes for releaseledger.

All releaseledger errors flow through :class:`ReleaseledgerError` (and the
:class:`LaunchError` subclass that services raise). The CLI catches these at the
command boundary and turns them into the deterministic JSON error envelope.
"""

from __future__ import annotations

__all__ = [
    "CODE_CONFIG_ERROR",
    "CODE_CONFLICT",
    "CODE_NOT_FOUND",
    "CODE_USAGE_ERROR",
    "CODE_VALIDATION_ERROR",
    "EXIT_RUNTIME",
    "EXIT_USAGE",
    "LaunchError",
    "ReleaseledgerError",
    "to_error_payload",
]

# Stable machine codes referenced across the CLI envelope.
CODE_USAGE_ERROR = "USAGE_ERROR"
CODE_NOT_FOUND = "NOT_FOUND"
CODE_CONFIG_ERROR = "CONFIG_ERROR"
CODE_VALIDATION_ERROR = "VALIDATION_ERROR"
CODE_CONFLICT = "CONFLICT"

# Exit codes: 2 for usage/config/validation input problems, 1 for runtime.
EXIT_USAGE = 2
EXIT_RUNTIME = 1


class ReleaseledgerError(Exception):
    """Base error for all releaseledger failures.

    Attributes:
        message: Human readable message.
        code: Stable machine code (see module-level constants).
        exit_code: Process exit code (2 for usage/config/validation, 1 runtime).
        data: Optional structured detail merged into the error payload.
        remediation: Optional ordered remediation hints.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "RELEASELEDGER_ERROR",
        exit_code: int = EXIT_RUNTIME,
        data: dict[str, object] | None = None,
        remediation: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.exit_code = exit_code
        self.data: dict[str, object] = dict(data) if data else {}
        self.remediation: list[str] = list(remediation) if remediation else []

    def to_payload(self) -> dict[str, object]:
        """Render a deterministic JSON-serializable error payload."""
        payload: dict[str, object] = {
            "code": self.code,
            "message": self.message,
            "exit_code": self.exit_code,
        }
        if self.remediation:
            payload["remediation"] = list(self.remediation)
        if self.data:
            payload["data"] = dict(self.data)
        return payload


class LaunchError(ReleaseledgerError):
    """Raised by services/cli helpers for actionable, user-facing failures.

    Services raise ``LaunchError`` (never ``typer.Exit`` and never print) so the
    CLI boundary can render either a human line or a JSON envelope.
    """


def to_error_payload(error: ReleaseledgerError) -> dict[str, object]:
    """Return the deterministic JSON-serializable error payload for an error."""
    return error.to_payload()
