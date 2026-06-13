"""Project-local TOML configuration for releaseledger.

This module owns parsing, validating, and rendering ``.releaseledger.toml``.
Path resolution relative to the config file lives in
:mod:`releaseledger.storage.paths`; this module deliberately has no filesystem
discovery so it can be unit-tested against plain dicts.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib  # type: ignore[import-not-found]

from releaseledger.errors import CODE_CONFIG_ERROR, CODE_USAGE_ERROR, LaunchError

__all__ = [
    "ALLOWED_LEDGER_KEYS",
    "ALLOWED_RELEASE_KEYS",
    "ALLOWED_TOP_LEVEL_KEYS",
    "CONFIG_VERSION",
    "DEFAULT_CHANGELOG",
    "DEFAULT_LEDGER_CODE",
    "DEFAULT_LEDGER_NAME",
    "DEFAULT_LEDGER_REF",
    "DEFAULT_RELEASE_STATUS",
    "ProjectConfig",
    "load_project_config",
    "project_name_or_default",
    "render_default_releaseledger_toml",
]

CONFIG_VERSION = 1
DEFAULT_LEDGER_REF = "main"
DEFAULT_LEDGER_CODE = "rl"
DEFAULT_LEDGER_NAME = "releaseledger"
DEFAULT_CHANGELOG = "CHANGELOG.md"
DEFAULT_RELEASE_STATUS = "planned"

ALLOWED_TOP_LEVEL_KEYS = {
    "config_version",
    "releaseledger_dir",
    "ledger_ref",
    "ledger_parent_ref",
    "ledger_next_entry_number",
    "ledger_branch_guard",
    "ledger",
    "release",
}
ALLOWED_LEDGER_KEYS = {"code", "name"}
ALLOWED_RELEASE_KEYS = {
    "default_changelog",
    "default_status",
    "allow_dirty_worktree",
}


@dataclass(frozen=True)
class ProjectConfig:
    """Parsed and validated project configuration values."""

    config_version: int = CONFIG_VERSION
    releaseledger_dir: str = ".releaseledger"
    ledger_ref: str = DEFAULT_LEDGER_REF
    ledger_parent_ref: str = ""
    ledger_next_entry_number: int = 1
    ledger_branch_guard: str = "off"
    ledger_code: str = DEFAULT_LEDGER_CODE
    ledger_name: str = DEFAULT_LEDGER_NAME
    default_changelog: str = DEFAULT_CHANGELOG
    default_status: str = DEFAULT_RELEASE_STATUS
    allow_dirty_worktree: bool = True


def _require_str(value: object, key: str, source: str) -> str:
    if not isinstance(value, str):
        raise LaunchError(
            f"Config key {key!r} in {source} must be a string.",
            code=CODE_CONFIG_ERROR,
            exit_code=2,
        )
    return value


def _require_bool(value: object, key: str, source: str) -> bool:
    if not isinstance(value, bool):
        raise LaunchError(
            f"Config key {key!r} in {source} must be a boolean.",
            code=CODE_CONFIG_ERROR,
            exit_code=2,
        )
    return value


def _require_int(value: object, key: str, source: str) -> int:
    # ``bool`` is a subclass of ``int``; reject it explicitly.
    if isinstance(value, bool) or not isinstance(value, int):
        raise LaunchError(
            f"Config key {key!r} in {source} must be an integer.",
            code=CODE_CONFIG_ERROR,
            exit_code=2,
        )
    return value


def _config_from_dict(data: dict[str, Any], source: str) -> ProjectConfig:
    unknown = sorted(k for k in data if k not in ALLOWED_TOP_LEVEL_KEYS)
    if unknown:
        raise LaunchError(
            f"Unknown config keys in {source}: {', '.join(unknown)}",
            code=CODE_CONFIG_ERROR,
            exit_code=2,
        )

    releaseledger_dir = _require_str(
        data.get("releaseledger_dir", ".releaseledger"), "releaseledger_dir", source
    )
    if not releaseledger_dir.strip():
        raise LaunchError(
            "Config key 'releaseledger_dir' must be a non-empty string.",
            code=CODE_CONFIG_ERROR,
            exit_code=2,
        )

    ledger_section = data.get("ledger", {})
    if not isinstance(ledger_section, dict):
        raise LaunchError(
            f"Config table 'ledger' in {source} must be a mapping.",
            code=CODE_CONFIG_ERROR,
            exit_code=2,
        )
    ledger_unknown = sorted(k for k in ledger_section if k not in ALLOWED_LEDGER_KEYS)
    if ledger_unknown:
        raise LaunchError(
            f"Unknown 'ledger' keys in {source}: {', '.join(ledger_unknown)}",
            code=CODE_CONFIG_ERROR,
            exit_code=2,
        )

    release_section = data.get("release", {})
    if not isinstance(release_section, dict):
        raise LaunchError(
            f"Config table 'release' in {source} must be a mapping.",
            code=CODE_CONFIG_ERROR,
            exit_code=2,
        )
    release_unknown = sorted(
        k for k in release_section if k not in ALLOWED_RELEASE_KEYS
    )
    if release_unknown:
        raise LaunchError(
            f"Unknown 'release' keys in {source}: {', '.join(release_unknown)}",
            code=CODE_CONFIG_ERROR,
            exit_code=2,
        )

    return ProjectConfig(
        config_version=_require_int(
            data.get("config_version", CONFIG_VERSION), "config_version", source
        ),
        releaseledger_dir=releaseledger_dir,
        ledger_ref=_require_str(
            data.get("ledger_ref", DEFAULT_LEDGER_REF), "ledger_ref", source
        ),
        ledger_parent_ref=_require_str(
            data.get("ledger_parent_ref", ""), "ledger_parent_ref", source
        ),
        ledger_next_entry_number=_require_int(
            data.get("ledger_next_entry_number", 1),
            "ledger_next_entry_number",
            source,
        ),
        ledger_branch_guard=_require_str(
            data.get("ledger_branch_guard", "off"), "ledger_branch_guard", source
        ),
        ledger_code=_require_str(
            ledger_section.get("code", DEFAULT_LEDGER_CODE), "ledger.code", source
        ),
        ledger_name=_require_str(
            ledger_section.get("name", DEFAULT_LEDGER_NAME), "ledger.name", source
        ),
        default_changelog=_require_str(
            release_section.get("default_changelog", DEFAULT_CHANGELOG),
            "release.default_changelog",
            source,
        ),
        default_status=_require_str(
            release_section.get("default_status", DEFAULT_RELEASE_STATUS),
            "release.default_status",
            source,
        ),
        allow_dirty_worktree=_require_bool(
            release_section.get("allow_dirty_worktree", True),
            "release.allow_dirty_worktree",
            source,
        ),
    )


def load_project_config(config_path: Path) -> ProjectConfig:
    """Load and validate the project TOML at ``config_path``."""
    if not config_path.is_file():
        raise LaunchError(
            f"Project config not found: {config_path}",
            code=CODE_CONFIG_ERROR,
            exit_code=2,
            remediation=["Run `releaseledger init` to create the config."],
        )
    try:
        with config_path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise LaunchError(
            f"Failed to parse {config_path.name}: {exc}",
            code=CODE_CONFIG_ERROR,
            exit_code=2,
        ) from exc
    return _config_from_dict(data, config_path.name)


def project_name_or_default(config_path: Path, workspace_root: Path) -> str:
    """Return the configured project name, falling back to the directory name."""
    if config_path.is_file():
        try:
            config = load_project_config(config_path)
        except LaunchError:
            config = ProjectConfig()
        if config.ledger_name and config.ledger_name != DEFAULT_LEDGER_NAME:
            return config.ledger_name
    return workspace_root.name or DEFAULT_LEDGER_NAME


def render_default_releaseledger_toml(
    *,
    releaseledger_dir: str = ".releaseledger",
    project_name: str = DEFAULT_LEDGER_NAME,
    ledger_ref: str = DEFAULT_LEDGER_REF,
) -> str:
    """Render the canonical default ``.releaseledger.toml`` content."""
    return f"""\
# Project-local releaseledger configuration.
# This file lives in the source project root.
config_version = {CONFIG_VERSION}
releaseledger_dir = "{releaseledger_dir}"

# Branch-scoped release state. This block is safe to commit.
ledger_ref = "{ledger_ref}"
ledger_parent_ref = ""
ledger_next_entry_number = 1
ledger_branch_guard = "off"

# Cross-ledger identity. Local record IDs stay unchanged; global refs are derived.
[ledger]
code = "{DEFAULT_LEDGER_CODE}"
name = "{project_name}"

# Release defaults.
[release]
default_changelog = "{DEFAULT_CHANGELOG}"
default_status = "{DEFAULT_RELEASE_STATUS}"
allow_dirty_worktree = true
"""


def validate_releaseledger_dir_value(value: str, *, source: str) -> str:
    """Validate a ``releaseledger_dir`` config value before writing/using it."""
    if not isinstance(value, str) or not value.strip():
        raise LaunchError(
            "releaseledger_dir must be a non-empty string.",
            code=CODE_USAGE_ERROR,
            exit_code=2,
        )
    return value
