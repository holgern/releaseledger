"""Release service: create, tag, finalize, list, and show releases.

Services return plain dict payloads and raise :class:`LaunchError`. They never
print or call ``typer.Exit``. Every mutation persists the record, appends one
event, and rebuilds the indexes.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import replace
from pathlib import Path

import ledgercore

from releaseledger.domain.event import (
    EVENT_RELEASE_CREATED,
    EVENT_RELEASE_FINALIZED,
    EVENT_RELEASE_TAGGED,
    EVENT_RELEASE_UPDATED,
)
from releaseledger.domain.release import ReleaseRecord
from releaseledger.domain.states import RELEASE_STATUSES
from releaseledger.errors import (
    CODE_CONFLICT,
    CODE_USAGE_ERROR,
    CODE_VALIDATION_ERROR,
    LaunchError,
)
from releaseledger.services.events import append_event
from releaseledger.storage.paths import resolve_project_paths
from releaseledger.storage.store import (
    list_releases,
    load_entries,
    load_release,
    rebuild_indexes,
    release_markdown_path,
    save_release,
    validate_release_version,
)

__all__ = [
    "create_release",
    "finalize_release",
    "list_release_records",
    "show_release",
    "tag_release",
    "update_release",
]

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_FINALIZABLE_STATUSES = frozenset({"planned", "draft", "candidate"})


def _today() -> str:
    return datetime.date.today().isoformat()


def _validate_date(value: str, field_name: str) -> str:
    if not _DATE_RE.fullmatch(value):
        raise LaunchError(
            f"{field_name} must be a YYYY-MM-DD date, got {value!r}.",
            code=CODE_USAGE_ERROR,
            exit_code=2,
        )
    return value


def _infer_previous_version(workspace_root: Path) -> str | None:
    """Return the latest released release version, or None if there is none."""
    released = [r for r in list_releases(workspace_root) if r.status == "released"]
    if not released:
        return None
    return released[-1].version


def _validate_source_metadata(
    *,
    boundary_ref: str | None,
    source_refs: tuple[str, ...],
    source_count: int | None,
) -> tuple[str | None, tuple[str, ...], int | None]:
    try:
        boundary = (
            ledgercore.parse_global_ref(boundary_ref).global_ref
            if boundary_ref is not None
            else None
        )
        refs = tuple(
            dict.fromkeys(
                ledgercore.parse_global_ref(ref).global_ref for ref in source_refs
            )
        )
    except ledgercore.IdFormatError as exc:
        raise LaunchError(
            f"Invalid release source reference: {exc}",
            code=CODE_VALIDATION_ERROR,
            exit_code=2,
        ) from exc
    if source_count is not None and source_count < 0:
        raise LaunchError(
            "--source-count must be zero or greater.",
            code=CODE_VALIDATION_ERROR,
            exit_code=2,
        )
    return boundary, refs, source_count


def _release_payload(
    workspace_root: Path,
    record: ReleaseRecord,
    event_id: str | None = None,
) -> dict[str, object]:
    paths = resolve_project_paths(workspace_root)
    payload: dict[str, object] = {
        "kind": "release",
        "ledger_ref": paths.ledger_ref,
        "release": record.to_dict(),
    }
    if event_id is not None:
        payload["events"] = [event_id]
    return payload


def _persist_new_release(
    workspace_root: Path,
    record: ReleaseRecord,
    *,
    event_name: str,
) -> dict[str, object]:
    paths = resolve_project_paths(workspace_root)
    if release_markdown_path(paths, record.version).is_file():
        raise LaunchError(
            f"Release version already exists: {record.version}",
            code=CODE_CONFLICT,
            exit_code=2,
            remediation=[f"Run `releaseledger release show {record.version}`."],
        )
    save_release(workspace_root, record, overwrite=False)
    event = append_event(
        workspace_root,
        event=event_name,
        release_version=record.version,
        data={"status": record.status},
    )
    rebuild_indexes(workspace_root)
    return _release_payload(workspace_root, record, event.event_id)


def create_release(
    workspace_root: Path,
    *,
    version: str,
    title: str | None = None,
    status: str = "planned",
    note: str | None = None,
    previous_version: str | None = None,
    changelog_file: str | None = None,
    released_at: str | None = None,
    boundary_ref: str | None = None,
    source_refs: tuple[str, ...] = (),
    source_count: int | None = None,
) -> dict[str, object]:
    """Create a new release record. Fails if the version already exists."""
    validate_release_version(version)
    if status not in RELEASE_STATUSES:
        raise LaunchError(
            f"Unsupported release status: {status!r}",
            code=CODE_VALIDATION_ERROR,
            exit_code=2,
        )
    if released_at is not None:
        _validate_date(released_at, "--released-at")
    if previous_version is None:
        previous_version = _infer_previous_version(workspace_root)
    boundary_ref, source_refs, source_count = _validate_source_metadata(
        boundary_ref=boundary_ref,
        source_refs=source_refs,
        source_count=source_count,
    )
    record = ReleaseRecord(
        version=version,
        status=status,
        title=title,
        released_at=released_at,
        previous_version=previous_version,
        note=note,
        changelog_file=changelog_file,
        boundary_ref=boundary_ref,
        source_refs=source_refs,
        source_count=source_count,
    )
    return _persist_new_release(
        workspace_root, record, event_name=EVENT_RELEASE_CREATED
    )


def tag_release(
    workspace_root: Path,
    *,
    version: str,
    note: str | None = None,
    previous_version: str | None = None,
    changelog_file: str | None = None,
    released_at: str | None = None,
    boundary_ref: str | None = None,
    source_refs: tuple[str, ...] = (),
    source_count: int | None = None,
) -> dict[str, object]:
    """Create a release with status 'released' (released_at defaults to today)."""
    validate_release_version(version)
    if released_at is not None:
        _validate_date(released_at, "--released-at")
    else:
        released_at = _today()
    if previous_version is None:
        previous_version = _infer_previous_version(workspace_root)
    boundary_ref, source_refs, source_count = _validate_source_metadata(
        boundary_ref=boundary_ref,
        source_refs=source_refs,
        source_count=source_count,
    )
    record = ReleaseRecord(
        version=version,
        status="released",
        title=f"Release {version}",
        released_at=released_at,
        previous_version=previous_version,
        note=note,
        changelog_file=changelog_file,
        boundary_ref=boundary_ref,
        source_refs=source_refs,
        source_count=source_count,
    )
    return _persist_new_release(workspace_root, record, event_name=EVENT_RELEASE_TAGGED)


def finalize_release(
    workspace_root: Path,
    *,
    version: str,
    released_at: str | None = None,
    changelog_file: str | None = None,
) -> dict[str, object]:
    """Transition an existing planned/draft/candidate release to 'released'."""
    validate_release_version(version)
    existing = load_release(workspace_root, version)
    if existing.status not in _FINALIZABLE_STATUSES:
        raise LaunchError(
            f"Release {version} is already {existing.status!r}"
            " and cannot be finalized.",
            code=CODE_CONFLICT,
            exit_code=2,
        )
    if released_at is not None:
        _validate_date(released_at, "--released-at")
    else:
        released_at = _today()
    updated = replace(
        existing,
        status="released",
        released_at=released_at,
        changelog_file=changelog_file or existing.changelog_file,
    )
    save_release(workspace_root, updated, overwrite=True)
    event = append_event(
        workspace_root,
        event=EVENT_RELEASE_FINALIZED,
        release_version=version,
        data={"released_at": released_at},
    )
    rebuild_indexes(workspace_root)
    return _release_payload(workspace_root, updated, event.event_id)


def update_release(
    workspace_root: Path,
    *,
    version: str,
    title: str | None = None,
    status: str | None = None,
    note: str | None = None,
    previous_version: str | None = None,
    changelog_file: str | None = None,
    boundary_ref: str | None = None,
    source_refs: tuple[str, ...] | None = None,
    source_count: int | None = None,
) -> dict[str, object]:
    """Update explicitly supplied release metadata."""
    existing = load_release(workspace_root, version)
    if status is not None and status not in RELEASE_STATUSES:
        raise LaunchError(
            f"Unsupported release status: {status!r}",
            code=CODE_VALIDATION_ERROR,
            exit_code=2,
        )
    boundary, refs, count = _validate_source_metadata(
        boundary_ref=(
            boundary_ref if boundary_ref is not None else existing.boundary_ref
        ),
        source_refs=source_refs if source_refs is not None else existing.source_refs,
        source_count=(
            source_count if source_count is not None else existing.source_count
        ),
    )
    values: dict[str, object] = {
        "title": title if title is not None else existing.title,
        "status": status if status is not None else existing.status,
        "note": note if note is not None else existing.note,
        "previous_version": (
            previous_version
            if previous_version is not None
            else existing.previous_version
        ),
        "changelog_file": (
            changelog_file if changelog_file is not None else existing.changelog_file
        ),
        "boundary_ref": boundary,
        "source_refs": refs,
        "source_count": count,
    }
    if all(getattr(existing, key) == value for key, value in values.items()):
        raise LaunchError(
            "Release update did not change any fields.",
            code=CODE_CONFLICT,
            exit_code=2,
        )
    updated = replace(
        existing,
        title=title if title is not None else existing.title,
        status=status if status is not None else existing.status,
        note=note if note is not None else existing.note,
        previous_version=(
            previous_version
            if previous_version is not None
            else existing.previous_version
        ),
        changelog_file=(
            changelog_file if changelog_file is not None else existing.changelog_file
        ),
        boundary_ref=boundary,
        source_refs=refs,
        source_count=count,
    )
    save_release(workspace_root, updated, overwrite=True)
    event = append_event(
        workspace_root,
        event=EVENT_RELEASE_UPDATED,
        release_version=version,
        data={
            "fields": sorted(
                key for key, value in values.items() if getattr(existing, key) != value
            )
        },
    )
    rebuild_indexes(workspace_root)
    return _release_payload(workspace_root, updated, event.event_id)


def list_release_records(workspace_root: Path) -> list[dict[str, object]]:
    """Return release dicts sorted deterministically."""
    return [record.to_dict() for record in list_releases(workspace_root)]


def show_release(workspace_root: Path, version: str) -> dict[str, object]:
    """Return a release with its entries for display."""
    record = load_release(workspace_root, version)
    entries = [entry.to_dict() for entry in load_entries(workspace_root, version)]
    payload = _release_payload(workspace_root, record)
    payload["entries"] = entries
    payload["entry_count"] = len(entries)
    return payload
