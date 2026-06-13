"""Config discovery and on-disk layout for releaseledger.

Knows how to find ``.releaseledger.toml`` upward from a start directory, resolve
the state directory (``.releaseledger/`` by default), and materialize the
release-bundle layout::

    .releaseledger/
      ledgers/
        <ledger_ref>/
          releases/
          events/
          indexes/

Path resolution rules:

* Relative ``releaseledger_dir`` resolves under the workspace root and must not
  escape it.
* Absolute ``releaseledger_dir`` is allowed (explicit override) and normalized.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import ledgercore

from releaseledger.errors import CODE_CONFLICT, CODE_USAGE_ERROR, LaunchError
from releaseledger.storage.config import (
    CONFIG_VERSION,
    DEFAULT_LEDGER_NAME,
    ProjectConfig,
    load_project_config,
    render_default_releaseledger_toml,
)

__all__ = [
    "CANONICAL_PROJECT_CONFIG_FILENAME",
    "DEFAULT_RELEASELEDGER_DIR_NAME",
    "PROJECT_CONFIG_FILENAMES",
    "ProjectLocator",
    "ProjectPaths",
    "discover_workspace_root",
    "ensure_layout",
    "find_project_config",
    "initialize_project",
    "load_project_locator",
    "require_project",
    "resolve_project_paths",
    "resolve_releaseledger_dir",
]

PROJECT_CONFIG_FILENAMES = (".releaseledger.toml", "releaseledger.toml")
CANONICAL_PROJECT_CONFIG_FILENAME = ".releaseledger.toml"
DEFAULT_RELEASELEDGER_DIR_NAME = ".releaseledger"


LocatorSource = Literal["explicit", "dotfile", "toml", "default"]


@dataclass(slots=True, frozen=True)
class ProjectLocator:
    """Resolved location of the project config and state directory."""

    workspace_root: Path
    config_path: Path
    releaseledger_dir: Path
    source: LocatorSource


@dataclass(slots=True, frozen=True)
class ProjectPaths:
    """Fully resolved on-disk paths for the active ledger."""

    workspace_root: Path
    releaseledger_dir: Path
    config_path: Path
    ledger_ref: str
    ledger_dir: Path
    releases_dir: Path
    events_dir: Path
    indexes_dir: Path
    releases_index_path: Path
    entries_index_path: Path
    events_path: Path


def find_project_config(start: Path) -> Path | None:
    """Search upward from ``start`` for a releaseledger config file."""
    search = start.resolve()
    if search.is_file():
        search = search.parent
    locator = ledgercore.locate_config(
        search,
        PROJECT_CONFIG_FILENAMES,
        default_filename=None,
    )
    if locator is None:
        return None
    return locator.config_path


def discover_workspace_root(start: Path) -> Path:
    """Return the directory that owns the project config, or ``start`` itself."""
    config_path = find_project_config(start)
    if config_path is not None:
        return config_path.parent.resolve()
    resolved = start.resolve()
    return resolved.parent if resolved.is_file() else resolved


def resolve_releaseledger_dir(workspace_root: Path, value: str) -> Path:
    """Resolve a ``releaseledger_dir`` value against the workspace root.

    Relative values must stay under the workspace root (no traversal escape).
    Absolute values are allowed as explicit overrides and normalized.
    """
    if not isinstance(value, str) or not value.strip():
        raise LaunchError(
            "releaseledger_dir must be a non-empty string.",
            code=CODE_USAGE_ERROR,
            exit_code=2,
        )
    candidate = Path(value)
    root = workspace_root.resolve()
    if candidate.is_absolute():
        return candidate.resolve()
    resolved = (root / value).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise LaunchError(
            f"releaseledger_dir escapes the workspace root: {value!r}",
            code=CODE_USAGE_ERROR,
            exit_code=2,
        ) from None
    return resolved


def load_project_locator(
    start: Path,
    *,
    releaseledger_dir_override: str | None = None,
) -> ProjectLocator:
    """Locate the project config and resolve the state directory.

    The ``source`` field records how the state directory was determined:
    ``explicit`` (override given), ``dotfile`` (canonical ``.releaseledger.toml``
    found), ``toml`` (non-canonical ``releaseledger.toml`` found), or
    ``default`` (no config found, default location assumed).
    """
    search = start.resolve()
    if search.is_file():
        search = search.parent

    config_path = find_project_config(search)
    if config_path is not None:
        workspace_root = config_path.parent.resolve()
        if releaseledger_dir_override is not None:
            releaseledger_dir = resolve_releaseledger_dir(
                workspace_root, releaseledger_dir_override
            )
            source: LocatorSource = "explicit"
        else:
            config = load_project_config(config_path)
            releaseledger_dir = resolve_releaseledger_dir(
                workspace_root, config.releaseledger_dir
            )
            source = (
                "dotfile"
                if config_path.name == CANONICAL_PROJECT_CONFIG_FILENAME
                else "toml"
            )
        return ProjectLocator(
            workspace_root=workspace_root,
            config_path=config_path,
            releaseledger_dir=releaseledger_dir,
            source=source,
        )

    # No config found: default to start as the workspace root.
    workspace_root = search
    if releaseledger_dir_override is not None:
        releaseledger_dir = resolve_releaseledger_dir(
            workspace_root, releaseledger_dir_override
        )
        source = "explicit"
    else:
        releaseledger_dir = workspace_root / DEFAULT_RELEASELEDGER_DIR_NAME
        source = "default"
    default_config_path = workspace_root / CANONICAL_PROJECT_CONFIG_FILENAME
    return ProjectLocator(
        workspace_root=workspace_root,
        config_path=default_config_path,
        releaseledger_dir=releaseledger_dir,
        source=source,
    )


def resolve_project_paths(workspace_root: Path) -> ProjectPaths:
    """Resolve all on-disk paths from the config at ``workspace_root``."""
    config_path = workspace_root / CANONICAL_PROJECT_CONFIG_FILENAME
    config: ProjectConfig = load_project_config(config_path)
    releaseledger_dir = resolve_releaseledger_dir(
        workspace_root, config.releaseledger_dir
    )
    ledger_dir = releaseledger_dir / "ledgers" / config.ledger_ref
    releases_dir = ledger_dir / "releases"
    events_dir = ledger_dir / "events"
    indexes_dir = ledger_dir / "indexes"
    return ProjectPaths(
        workspace_root=workspace_root,
        releaseledger_dir=releaseledger_dir,
        config_path=config_path,
        ledger_ref=config.ledger_ref,
        ledger_dir=ledger_dir,
        releases_dir=releases_dir,
        events_dir=events_dir,
        indexes_dir=indexes_dir,
        releases_index_path=indexes_dir / "releases.json",
        entries_index_path=indexes_dir / "entries.json",
        events_path=events_dir / "events.jsonl",
    )


def _write_empty_index(path: Path) -> None:
    if path.exists():
        return
    ledgercore.ensure_dir(path.parent)
    ledgercore.write_json(path, [])


def ensure_layout(workspace_root: Path) -> ProjectPaths:
    """Create the release-bundle directory layout and empty indexes if missing."""
    paths = resolve_project_paths(workspace_root)
    ledgercore.ensure_dir(paths.releases_dir)
    ledgercore.ensure_dir(paths.events_dir)
    ledgercore.ensure_dir(paths.indexes_dir)
    _write_empty_index(paths.releases_index_path)
    _write_empty_index(paths.entries_index_path)
    return paths


def require_project(start: Path) -> ProjectPaths:
    """Resolve paths for an initialized project or raise a NOT_FOUND error."""
    config_path = find_project_config(start)
    if config_path is None:
        raise LaunchError(
            "Project not initialized: no .releaseledger.toml found.",
            code="NOT_FOUND",
            exit_code=2,
            remediation=["Run `releaseledger init` to initialize the project."],
        )
    return resolve_project_paths(config_path.parent.resolve())


def initialize_project(
    workspace_root: Path,
    *,
    releaseledger_dir: str | None = None,
    project_name: str | None = None,
    force: bool = False,
) -> dict[str, object]:
    """Create ``.releaseledger.toml`` and the default state layout.

    Returns a dict describing what was written for CLI rendering. Raises
    ``LaunchError`` (CONFLICT) when the config already exists unless ``force``.
    """
    workspace_root = workspace_root.resolve()
    config_path = workspace_root / CANONICAL_PROJECT_CONFIG_FILENAME
    if config_path.is_file() and not force:
        raise LaunchError(
            f"{config_path.name} already exists in {workspace_root}.",
            code=CODE_CONFLICT,
            exit_code=2,
            remediation=["Use --force to overwrite the existing config."],
        )

    dir_value = releaseledger_dir or DEFAULT_RELEASELEDGER_DIR_NAME
    # Validate the chosen value before writing so init fails fast.
    resolve_releaseledger_dir(workspace_root, dir_value)

    toml_text = render_default_releaseledger_toml(
        releaseledger_dir=dir_value,
        project_name=project_name or DEFAULT_LEDGER_NAME,
    )
    ledgercore.atomic_write_text(config_path, toml_text)
    paths = ensure_layout(workspace_root)

    return {
        "kind": "project_init",
        "workspace_root": str(workspace_root),
        "config_path": str(config_path),
        "releaseledger_dir": str(paths.releaseledger_dir),
        "ledger_ref": paths.ledger_ref,
        "ledger_dir": str(paths.ledger_dir),
        "config_version": CONFIG_VERSION,
        "created": {
            "releases_dir": str(paths.releases_dir),
            "events_dir": str(paths.events_dir),
            "indexes_dir": str(paths.indexes_dir),
        },
    }
