"""Console entry point shim for ``releaseledger``."""

from __future__ import annotations

from releaseledger.cli import app


def main() -> None:
    """Entry point referenced by ``project.scripts``."""
    app()
