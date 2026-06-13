"""Release entry domain model.

A :class:`ReleaseEntryRecord` is persisted as ``entry-NNNN.md`` inside a release
bundle. The ``body`` field is the Markdown body of the file and is excluded from
front matter.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import ledgercore

from releaseledger.domain.states import (
    ENTRY_KINDS,
    RELEASELEDGER_FILE_VERSION,
    RELEASELEDGER_SCHEMA_VERSION,
    SUPPORTED_SCHEMA_VERSIONS,
)
from releaseledger.errors import CODE_VALIDATION_ERROR, LaunchError

__all__ = [
    "ENTRY_FRONT_MATTER_KEY_ORDER",
    "ReleaseEntryRecord",
]

ENTRY_FRONT_MATTER_KEY_ORDER = (
    "schema_version",
    "object_type",
    "file_version",
    "entry_id",
    "release_version",
    "kind",
    "summary",
    "created_at",
    "paths",
    "issues",
    "prs",
    "sources",
    "breaking",
    "internal",
    "order",
)


@dataclass(slots=True, frozen=True)
class ReleaseEntryRecord:
    """A single changelog entry attached to a release."""

    entry_id: str
    release_version: str
    kind: str
    summary: str
    body: str | None = None
    created_at: str = field(default_factory=ledgercore.utc_now_iso)
    paths: tuple[str, ...] = ()
    issues: tuple[str, ...] = ()
    prs: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    breaking: bool = False
    internal: bool = False
    order: int | None = None
    file_version: str = RELEASELEDGER_FILE_VERSION
    schema_version: int = RELEASELEDGER_SCHEMA_VERSION
    object_type: str = "release_entry"

    def to_dict(self) -> dict[str, object]:
        """Full machine-readable representation (includes body)."""
        return {
            "schema_version": self.schema_version,
            "object_type": self.object_type,
            "file_version": self.file_version,
            "entry_id": self.entry_id,
            "release_version": self.release_version,
            "kind": self.kind,
            "summary": self.summary,
            "body": self.body,
            "created_at": self.created_at,
            "paths": list(self.paths),
            "issues": list(self.issues),
            "prs": list(self.prs),
            "sources": list(self.sources),
            "breaking": self.breaking,
            "internal": self.internal,
            "order": self.order,
        }

    def to_front_matter(self) -> dict[str, object]:
        """Front-matter representation (body is the file body, not front matter)."""
        data = self.to_dict()
        data.pop("body", None)
        return data


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise LaunchError(
            f"Entry field {field_name!r} must be a string.",
            code=CODE_VALIDATION_ERROR,
            exit_code=2,
        )
    return value


def _require_optional_str(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_str(value, field_name)


def _require_str_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise LaunchError(
            f"Entry field {field_name!r} must be a list.",
            code=CODE_VALIDATION_ERROR,
            exit_code=2,
        )
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise LaunchError(
                f"Entry field {field_name!r} must contain only strings.",
                code=CODE_VALIDATION_ERROR,
                exit_code=2,
            )
        items.append(item)
    return tuple(items)


def _require_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise LaunchError(
            f"Entry field {field_name!r} must be a boolean.",
            code=CODE_VALIDATION_ERROR,
            exit_code=2,
        )
    return value


def _require_optional_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise LaunchError(
            f"Entry field {field_name!r} must be an integer.",
            code=CODE_VALIDATION_ERROR,
            exit_code=2,
        )
    return value


def entry_from_dict(data: dict[str, object]) -> ReleaseEntryRecord:
    """Build a :class:`ReleaseEntryRecord` with strict validation."""
    if data.get("object_type") != "release_entry":
        raise LaunchError(
            "Entry record object_type must be 'release_entry'.",
            code=CODE_VALIDATION_ERROR,
            exit_code=2,
        )
    schema_version = data.get("schema_version")
    if (
        not isinstance(schema_version, int)
        or schema_version not in SUPPORTED_SCHEMA_VERSIONS
    ):
        raise LaunchError(
            f"Unsupported entry schema_version: {schema_version!r}",
            code=CODE_VALIDATION_ERROR,
            exit_code=2,
        )
    entry_id = data.get("entry_id")
    if not isinstance(entry_id, str) or not entry_id.strip():
        raise LaunchError(
            "Entry entry_id must be a non-empty string.",
            code=CODE_VALIDATION_ERROR,
            exit_code=2,
        )
    release_version = data.get("release_version")
    if not isinstance(release_version, str) or not release_version.strip():
        raise LaunchError(
            "Entry release_version must be a non-empty string.",
            code=CODE_VALIDATION_ERROR,
            exit_code=2,
        )
    kind = data.get("kind")
    if kind not in ENTRY_KINDS:
        raise LaunchError(
            f"Unsupported entry kind: {kind!r}",
            code=CODE_VALIDATION_ERROR,
            exit_code=2,
        )
    summary = data.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise LaunchError(
            "Entry summary must be a non-empty string.",
            code=CODE_VALIDATION_ERROR,
            exit_code=2,
        )
    return ReleaseEntryRecord(
        entry_id=entry_id,
        release_version=release_version,
        kind=kind,
        summary=summary,
        body=_require_optional_str(data.get("body"), "body"),
        created_at=_require_str(data.get("created_at", ""), "created_at"),
        paths=_require_str_tuple(data.get("paths", []), "paths"),
        issues=_require_str_tuple(data.get("issues", []), "issues"),
        prs=_require_str_tuple(data.get("prs", []), "prs"),
        sources=_require_str_tuple(data.get("sources", []), "sources"),
        breaking=_require_bool(data.get("breaking", False), "breaking"),
        internal=_require_bool(data.get("internal", False), "internal"),
        order=_require_optional_int(data.get("order"), "order"),
        file_version=_require_str(
            data.get("file_version", RELEASELEDGER_FILE_VERSION), "file_version"
        ),
        schema_version=schema_version,
        object_type="release_entry",
    )
