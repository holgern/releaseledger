"""Validated per-record revision metadata."""

from __future__ import annotations

from dataclasses import dataclass, replace

from releaseledger.errors import CODE_VALIDATION_ERROR, LaunchError

VERSIONING_SCHEMA_VERSION = 1


@dataclass(slots=True, frozen=True)
class RecordVersioning:
    revision: int = 1
    schema_version: int = VERSIONING_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": self.schema_version, "revision": self.revision}


def versioning_from_dict(
    value: object, *, field_name: str = "versioning"
) -> RecordVersioning:
    if not isinstance(value, dict):
        raise LaunchError(
            f"{field_name} must be a mapping.",
            code=CODE_VALIDATION_ERROR,
            exit_code=2,
        )
    schema_version = value.get("schema_version")
    revision = value.get("revision")
    if schema_version != VERSIONING_SCHEMA_VERSION:
        raise LaunchError(
            f"Unsupported {field_name}.schema_version: {schema_version!r}",
            code=CODE_VALIDATION_ERROR,
            exit_code=2,
        )
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise LaunchError(
            f"{field_name}.revision must be a positive integer.",
            code=CODE_VALIDATION_ERROR,
            exit_code=2,
        )
    return RecordVersioning(schema_version=schema_version, revision=revision)


def initial_versioning() -> RecordVersioning:
    return RecordVersioning()


def bump_versioning(value: RecordVersioning) -> RecordVersioning:
    return replace(value, revision=value.revision + 1)
