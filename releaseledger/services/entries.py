"""Entry service: add and list changelog entries for a release.

Adding an entry validates inputs, assigns the next monotonic id/order, persists
the entry, bumps the parent release's ``entry_count``, appends an event, and
rebuilds the indexes.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import ledgercore

from releaseledger.domain.entry import ReleaseEntryRecord
from releaseledger.domain.event import EVENT_ENTRY_ADDED
from releaseledger.domain.states import ENTRY_KINDS
from releaseledger.errors import CODE_VALIDATION_ERROR, LaunchError
from releaseledger.services.events import append_event
from releaseledger.storage.paths import resolve_project_paths
from releaseledger.storage.store import (
    load_entries,
    load_release,
    rebuild_indexes,
    save_entry,
    save_release,
)

__all__ = ["add_release_entry", "list_release_entries"]


def _validate_paths(paths: tuple[str, ...]) -> tuple[str, ...]:
    validated: list[str] = []
    for raw in paths:
        try:
            validated.append(
                ledgercore.validate_relative_posix_path(raw, field_name="--path")
            )
        except ledgercore.PathValidationError as exc:
            raise LaunchError(
                str(exc),
                code=CODE_VALIDATION_ERROR,
                exit_code=2,
            ) from exc
    return tuple(validated)


def add_release_entry(
    workspace_root: Path,
    *,
    release_version: str,
    kind: str,
    summary: str,
    body: str | None = None,
    paths: tuple[str, ...] = (),
    issues: tuple[str, ...] = (),
    prs: tuple[str, ...] = (),
    sources: tuple[str, ...] = (),
    breaking: bool = False,
    internal: bool = False,
) -> dict[str, object]:
    """Add a changelog entry to an existing release."""
    # Release existence check (raises NOT_FOUND if missing).
    release = load_release(workspace_root, release_version)
    if kind not in ENTRY_KINDS:
        raise LaunchError(
            f"Unsupported entry kind: {kind!r}",
            code=CODE_VALIDATION_ERROR,
            exit_code=2,
        )
    if not isinstance(summary, str) or not summary.strip():
        raise LaunchError(
            "Entry summary must be a non-empty string.",
            code=CODE_VALIDATION_ERROR,
            exit_code=2,
        )
    safe_paths = _validate_paths(paths)
    entries = load_entries(workspace_root, release_version)
    entry_id = next_entry_id_from(entries)
    order = len(entries) + 1
    record = ReleaseEntryRecord(
        entry_id=entry_id,
        release_version=release.version,
        kind=kind,
        summary=summary,
        body=body,
        paths=safe_paths,
        issues=tuple(issues),
        prs=tuple(prs),
        sources=tuple(sources),
        breaking=breaking,
        internal=internal,
        order=order,
    )
    save_entry(workspace_root, record)
    updated_release = replace(release, entry_count=len(entries) + 1)
    save_release(workspace_root, updated_release, overwrite=True)
    event = append_event(
        workspace_root,
        event=EVENT_ENTRY_ADDED,
        release_version=release.version,
        entry_id=entry_id,
        data={"kind": kind},
    )
    rebuild_indexes(workspace_root)
    paths_obj = resolve_project_paths(workspace_root)
    return {
        "kind": "release_entry",
        "ledger_ref": paths_obj.ledger_ref,
        "release_version": release.version,
        "entry": record.to_dict(),
        "events": [event.event_id],
    }


def next_entry_id_from(entries: list[ReleaseEntryRecord]) -> str:
    """Return the next ``entry-NNNN`` id given existing entries."""
    return ledgercore.next_prefixed_id("entry", [e.entry_id for e in entries])


def list_release_entries(
    workspace_root: Path,
    release_version: str,
) -> list[dict[str, object]]:
    """Return entry dicts for a release (release must exist)."""
    load_release(workspace_root, release_version)
    return [entry.to_dict() for entry in load_entries(workspace_root, release_version)]
