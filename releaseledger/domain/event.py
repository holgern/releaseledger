"""Release event domain model, appended to ``events.jsonl`` on every mutation."""

from __future__ import annotations

from dataclasses import dataclass, field

from releaseledger.domain.states import (
    RELEASELEDGER_SCHEMA_VERSION,
    SUPPORTED_SCHEMA_VERSIONS,
)
from releaseledger.errors import CODE_VALIDATION_ERROR, LaunchError

__all__ = ["ReleaseEvent"]

# Recognized event names for documentation/typing; unknown events are still
# persisted to keep the append log forward-compatible.
EVENT_RELEASE_CREATED = "release.created"
EVENT_RELEASE_TAGGED = "release.tagged"
EVENT_RELEASE_FINALIZED = "release.finalized"
EVENT_RELEASE_UPDATED = "release.updated"
EVENT_RELEASE_CANCELED = "release.canceled"
EVENT_RELEASE_RENAMED = "release.renamed"
EVENT_RELEASE_CHAIN_REPAIRED = "release.chain_repaired"
EVENT_CHANGELOG_SECTION_RENAMED = "changelog.section_renamed"
EVENT_CHANGELOG_SECTION_REMOVED = "changelog.section_removed"
EVENT_ENTRY_ADDED = "entry.added"
EVENT_ENTRY_UPDATED = "entry.updated"
EVENT_ENTRY_IMPORTED = "entry.imported"
EVENT_ENTRY_BATCH_ADDED = "entry.batch_added"


@dataclass(slots=True, frozen=True)
class ReleaseEvent:
    """A single mutation event recorded in the ledger event log."""

    event_id: str
    ts: str
    event: str
    release_version: str | None = None
    entry_id: str | None = None
    data: dict[str, object] = field(default_factory=dict)
    schema_version: int = RELEASELEDGER_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        """JSONL-serializable representation (sorted keys on write)."""
        payload: dict[str, object] = {
            "event_id": self.event_id,
            "ts": self.ts,
            "event": self.event,
            "schema_version": self.schema_version,
        }
        if self.release_version is not None:
            payload["release_version"] = self.release_version
        if self.entry_id is not None:
            payload["entry_id"] = self.entry_id
        if self.data:
            payload["data"] = dict(self.data)
        return payload


def event_from_dict(data: dict[str, object]) -> ReleaseEvent:
    """Reconstruct a :class:`ReleaseEvent` from a JSONL row."""
    schema_version = data.get("schema_version")
    if (
        not isinstance(schema_version, int)
        or schema_version not in SUPPORTED_SCHEMA_VERSIONS
    ):
        raise LaunchError(
            f"Unsupported event schema_version: {schema_version!r}",
            code=CODE_VALIDATION_ERROR,
            exit_code=2,
        )
    event_id = data.get("event_id")
    ts = data.get("ts")
    event = data.get("event")
    if not isinstance(event_id, str):
        raise LaunchError(
            "Event event_id must be a string.", code=CODE_VALIDATION_ERROR
        )
    if not isinstance(ts, str):
        raise LaunchError("Event ts must be a string.", code=CODE_VALIDATION_ERROR)
    if not isinstance(event, str):
        raise LaunchError("Event event must be a string.", code=CODE_VALIDATION_ERROR)
    release_version = data.get("release_version")
    entry_id = data.get("entry_id")
    raw_data = data.get("data", {})
    if not isinstance(raw_data, dict):
        raise LaunchError("Event data must be a mapping.", code=CODE_VALIDATION_ERROR)
    return ReleaseEvent(
        event_id=event_id,
        ts=ts,
        event=event,
        release_version=release_version if isinstance(release_version, str) else None,
        entry_id=entry_id if isinstance(entry_id, str) else None,
        data=dict(raw_data),
        schema_version=schema_version,
    )
