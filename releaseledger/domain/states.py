"""Schema version constants and the controlled vocabularies for records."""

from __future__ import annotations

__all__ = [
    "ENTRY_KINDS",
    "ENTRY_KIND_ALIASES",
    "ENTRY_KIND_TITLES",
    "ENTRY_STATUSES",
    "RELEASE_STATUSES",
    "RELEASELEDGER_FILE_VERSION",
    "RELEASELEDGER_SCHEMA_VERSION",
    "SUPPORTED_SCHEMA_VERSIONS",
]

RELEASELEDGER_SCHEMA_VERSION = 1
RELEASELEDGER_FILE_VERSION = "releaseledger.v1"

SUPPORTED_SCHEMA_VERSIONS = frozenset({1})

RELEASE_STATUSES = frozenset(
    {
        "planned",
        "draft",
        "candidate",
        "released",
        "yanked",
    }
)

ENTRY_KINDS = frozenset(
    {
        "added",
        "changed",
        "fixed",
        "removed",
        "deprecated",
        "security",
        "docs",
        "quality",
        "internal",
    }
)

ENTRY_KIND_ALIASES = {
    "documentation": "docs",
    "doc": "docs",
}

ENTRY_STATUSES = frozenset({"draft", "accepted", "rejected"})

# Human-readable changelog group titles keyed by entry kind.
ENTRY_KIND_TITLES = {
    "added": "Added",
    "changed": "Changed",
    "fixed": "Fixed",
    "removed": "Removed",
    "deprecated": "Deprecated",
    "security": "Security",
    "docs": "Documentation",
    "quality": "Quality",
    "internal": "Internal",
}
