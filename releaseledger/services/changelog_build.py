"""Changelog build service.

Renders a final, template-driven changelog section for a release and inserts or
replaces it deterministically in the target ``CHANGELOG.md``. This is distinct
from :mod:`releaseledger.services.changelog`, which renders agent-facing changelog
*source/context*; this module renders the *final* human changelog section.

The data source is releaseledger release records and ``ReleaseEntryRecord``
entries — never Git commits. Templates use a sandboxed Jinja2 environment
(``{{ ... }}`` expressions, ``{% ... %}`` statements) and may access
``project``, ``release``, ``entries``, ``groups``, and ``releases``.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import ledgercore
from jinja2 import StrictUndefined
from jinja2.exceptions import SecurityError, TemplateError
from jinja2.sandbox import SandboxedEnvironment

from releaseledger.domain.entry import ReleaseEntryRecord, normalize_entry_status
from releaseledger.domain.release import ReleaseRecord
from releaseledger.domain.states import ENTRY_KIND_TITLES
from releaseledger.errors import (
    CODE_CONFLICT,
    CODE_NOT_FOUND,
    CODE_USAGE_ERROR,
    CODE_VALIDATION_ERROR,
    LaunchError,
)
from releaseledger.services.entry_lint import lint_release_entries
from releaseledger.storage.config import (
    DEFAULT_CHANGELOG,
    ProjectConfig,
    load_project_config,
)
from releaseledger.storage.paths import ProjectPaths, resolve_project_paths
from releaseledger.storage.store import list_releases, load_entries, load_release

__all__ = [
    "build_changelog_file",
    "build_changelog_render_context",
    "find_release_section",
    "insert_release_section",
    "remove_release_section",
    "rename_release_section",
    "render_changelog_section",
    "replace_release_section",
]

# Fixed group order for rendered changelog output (mirrors changelog.py).
_GROUP_ORDER = (
    "added",
    "changed",
    "fixed",
    "removed",
    "deprecated",
    "security",
    "docs",
    "quality",
    "internal",
)

# ``--release-date`` must be an ISO calendar date.
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Release section heading detection: ``## [1.2.0] ...`` or ``## 1.2.0 ...``.
_HEADING_RE_TEMPLATE = r"^## \[?{version}\]?\b.*$"

# Top-level (``#``) and second-level (``##``) heading line detection.
_TOP_TITLE_RE = re.compile(r"^#\s+\S")
_LEVEL2_RE = re.compile(r"^##\s+\S")
_UNRELEASED_RE = re.compile(r"^##\s+\[?\s*Unreleased\s*\]?\s*$", re.IGNORECASE)


def _project_name(paths: ProjectPaths) -> str:
    try:
        config = load_project_config(paths.config_path)
        return config.ledger_name or paths.workspace_root.name or "releaseledger"
    except Exception:  # pragma: no cover - defensive fallback
        return paths.workspace_root.name or "releaseledger"


def _load_config(paths: ProjectPaths) -> ProjectConfig:
    try:
        return load_project_config(paths.config_path)
    except LaunchError:
        return ProjectConfig()


def _entry_payload(entry: ReleaseEntryRecord) -> dict[str, object]:
    return {
        "entry_id": entry.entry_id,
        "kind": entry.kind,
        "title": ENTRY_KIND_TITLES.get(entry.kind, entry.kind.capitalize()),
        "summary": entry.summary,
        "body": entry.body,
        "paths": list(entry.paths),
        "issues": list(entry.issues),
        "prs": list(entry.prs),
        "sources": list(entry.sources),
        "status": entry.status,
        "audience": entry.audience,
        "scopes": list(entry.scopes),
        "source_refs": list(entry.source_refs),
        "breaking": entry.breaking,
        "internal": entry.internal,
    }


def _grouped_entries(
    entries: list[ReleaseEntryRecord],
) -> list[tuple[str, list[dict[str, object]]]]:
    grouped: list[tuple[str, list[dict[str, object]]]] = []
    for kind in _GROUP_ORDER:
        members = [_entry_payload(e) for e in entries if e.kind == kind]
        if members:
            grouped.append((kind, members))
    return grouped


def _groups_payload(
    grouped: list[tuple[str, list[dict[str, object]]]],
) -> list[dict[str, object]]:
    return [
        {
            "kind": kind,
            "title": ENTRY_KIND_TITLES.get(kind, kind.capitalize()),
            "entries": members,
        }
        for kind, members in grouped
    ]


def _effective_date(
    *,
    release: ReleaseRecord,
    release_date: str | None,
    unreleased: bool,
) -> str | None:
    if unreleased:
        return None
    return release_date or release.released_at


def _resolve_release_date(value: str | None) -> str | None:
    if value is None:
        return None
    if not _DATE_RE.match(value):
        raise LaunchError(
            f"Invalid --release-date {value!r}; expected YYYY-MM-DD.",
            code=CODE_VALIDATION_ERROR,
            exit_code=2,
        )
    return value


def build_changelog_render_context(
    workspace_root: Path,
    *,
    version: str,
    include_internal: bool = False,
    release_date: str | None = None,
    unreleased: bool = False,
    include_statuses: tuple[str, ...] = ("accepted",),
) -> dict[str, object]:
    """Build the deterministic render context for ``version``.

    The context exposes ``project``, ``release``, ``entries``, ``groups``, and
    ``releases``. Internal entries are filtered unless ``include_internal`` is
    true. ``release.date``/``release.released_at`` reflect the effective date:
    ``--release-date`` overrides ``released_at``; ``--unreleased`` forces None.
    """
    paths = resolve_project_paths(workspace_root)
    release = load_release(workspace_root, version)
    all_entries = load_entries(workspace_root, version)
    statuses = tuple(normalize_entry_status(value) for value in include_statuses)
    entries = [
        entry
        for entry in all_entries
        if entry.status in statuses and (include_internal or not entry.internal)
    ]
    project_name = _project_name(paths)
    effective_date = _effective_date(
        release=release,
        release_date=_resolve_release_date(release_date),
        unreleased=unreleased,
    )
    grouped = _grouped_entries(entries)

    release_payload: dict[str, object] = {
        "version": release.version,
        "title": release.title or f"Release {release.version}",
        "status": release.status,
        "date": effective_date,
        "released_at": effective_date,
        "previous_version": release.previous_version,
        "changelog_file": release.changelog_file,
        "entry_count": len(entries),
        "boundary_ref": release.boundary_ref,
        "source_refs": list(release.source_refs),
    }

    releases_list: list[dict[str, object]] = []
    try:
        for record in list_releases(workspace_root):
            releases_list.append(
                {
                    "version": record.version,
                    "date": record.released_at,
                }
            )
    except Exception:  # pragma: no cover - defensive: list is best-effort
        releases_list = []

    status_counts = {
        status: sum(entry.status == status for entry in all_entries)
        for status in ("accepted", "draft", "rejected")
    }
    warnings: list[str] = []
    if "draft" in statuses and status_counts["draft"]:
        warnings.append("Draft entries are included; output is draft-quality.")
    return {
        "project": {"name": project_name},
        "release": release_payload,
        "entries": [_entry_payload(e) for e in entries],
        "groups": _groups_payload(grouped),
        "releases": releases_list,
        "included_statuses": list(statuses),
        "status_counts": status_counts,
        "warnings": warnings,
    }


def _make_environment(
    *, trim_blocks: bool, lstrip_blocks: bool
) -> SandboxedEnvironment:
    env = SandboxedEnvironment(
        trim_blocks=trim_blocks,
        lstrip_blocks=lstrip_blocks,
        keep_trailing_newline=False,
        autoescape=False,
        undefined=StrictUndefined,
    )
    return env


def _render_template(
    env: SandboxedEnvironment, source: str, context: dict[str, object]
) -> str:
    try:
        template = env.from_string(source)
        return template.render(**context)
    except SecurityError as exc:
        raise LaunchError(
            f"Changelog template rejected for security: {exc}",
            code=CODE_VALIDATION_ERROR,
            exit_code=2,
        ) from exc
    except TemplateError as exc:
        raise LaunchError(
            f"Changelog template render failed: {exc}",
            code=CODE_VALIDATION_ERROR,
            exit_code=2,
        ) from exc


def _trim_section(text: str) -> str:
    """Collapse 3+ consecutive newlines to a single blank line and strip ends."""
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip("\n")


def _literal_replacer(replacement: str) -> Callable[[re.Match[str]], str]:
    """Build a typed re.sub callback for literal (non-backreference) replace."""

    def _replace(_match: re.Match[str]) -> str:
        return replacement

    return _replace


def _apply_postprocessors(text: str, postprocessors: tuple[dict[str, str], ...]) -> str:
    for step in postprocessors:
        # Literal replacement: a closure returning the replacement so the
        # replacement string is never interpreted for backreferences.
        text = re.sub(step["pattern"], _literal_replacer(step["replace"]), text)
    return text


def _extract_heading(section: str) -> str | None:
    for line in section.splitlines():
        if _LEVEL2_RE.match(line):
            return line.strip()
    return None


def render_changelog_section(
    workspace_root: Path,
    *,
    version: str,
    include_internal: bool = False,
    release_date: str | None = None,
    unreleased: bool = False,
    template_name: str = "default",
    include_statuses: tuple[str, ...] = ("accepted",),
) -> dict[str, object]:
    """Render the final changelog section for ``version`` without writing files.

    Returns render metadata and the section text. The section has exactly one
    trailing newline. ``section_heading`` is the first ``## `` line in the
    rendered section (or None if the template produced none).
    """
    paths = resolve_project_paths(workspace_root)
    config = _load_config(paths)
    context = build_changelog_render_context(
        workspace_root,
        version=version,
        include_internal=include_internal,
        release_date=release_date,
        unreleased=unreleased,
        include_statuses=include_statuses,
    )

    trim_blocks = bool(config.changelog_trim)
    env = _make_environment(trim_blocks=trim_blocks, lstrip_blocks=trim_blocks)
    render_context = dict(context)

    parts: list[str] = []
    header = config.changelog_header
    if header.strip():
        parts.append(_render_template(env, header, render_context))
    parts.append(_render_template(env, config.changelog_body, render_context))
    footer = config.changelog_footer
    if footer.strip():
        parts.append(_render_template(env, footer, render_context))

    section = "\n\n".join(part for part in parts if part)
    if config.changelog_trim:
        section = _trim_section(section)
    section = _apply_postprocessors(section, config.changelog_postprocessors)
    # Normalize newlines and ensure exactly one final newline.
    section = ledgercore.normalize_newlines(section)
    section = section.strip("\n") + "\n"

    release_payload = context["release"]
    assert isinstance(release_payload, dict)
    entry_count = int(release_payload.get("entry_count", 0))
    effective_date = release_payload.get("date")

    warnings: list[str] = []
    context_warnings = context.get("warnings", [])
    if isinstance(context_warnings, list):
        warnings.extend(str(item) for item in context_warnings)
    if entry_count == 0 and not config.changelog_render_always:
        warnings.append("Release has no changelog entries; rendered an empty section.")

    return {
        "kind": "changelog_build",
        "version": version,
        "section": section,
        "section_heading": _extract_heading(section),
        "entry_count": entry_count,
        "included_internal": bool(include_internal),
        "release_date": effective_date,
        "template_name": template_name,
        "warnings": warnings,
        "included_statuses": context["included_statuses"],
        "status_counts": context["status_counts"],
    }


@dataclass(frozen=True)
class _Span:
    start: int  # line index (inclusive)
    end: int  # line index (exclusive)


def find_release_section(text: str, version: str) -> _Span | None:
    """Locate an existing release section for ``version``.

    Returns the inclusive-start, exclusive-end line indices, or None if the
    version heading is absent. The section runs from its ``## [?]VERSION[?]``
    heading through just before the next ``## `` heading or EOF.
    """
    escaped = re.escape(version)
    heading_re = re.compile(_HEADING_RE_TEMPLATE.format(version=escaped), re.MULTILINE)
    lines = text.splitlines(keepends=True)
    heading_line_index: int | None = None
    for index, line in enumerate(lines):
        if heading_re.match(line):
            heading_line_index = index
            break
    if heading_line_index is None:
        return None
    end = len(lines)
    for index in range(heading_line_index + 1, len(lines)):
        if _LEVEL2_RE.match(lines[index]):
            end = index
            break
    return _Span(start=heading_line_index, end=end)


def _ensure_final_newline(text: str) -> str:
    text = ledgercore.normalize_newlines(text)
    if text == "":
        return text
    return text if text.endswith("\n") else text + "\n"


def insert_release_section(text: str, section: str) -> str:
    """Insert a rendered release section into existing changelog ``text``.

    Insertion precedence:
    1. below ``## Unreleased`` (before the next ``## `` heading), if present;
    2. before the first ``## `` heading, if any;
    3. after the title/intro (first ``# `` line and following non-heading lines);
    4. otherwise create a new changelog with a ``# Changelog`` title.

    ``section`` must already have exactly one trailing newline.
    """
    lines = text.splitlines(keepends=True)
    section = _ensure_final_newline(section)

    # 1. Below ## Unreleased.
    unreleased_idx = next(
        (i for i, line in enumerate(lines) if _UNRELEASED_RE.match(line)), None
    )
    if unreleased_idx is not None:
        insert_at = len(lines)
        for index in range(unreleased_idx + 1, len(lines)):
            if _LEVEL2_RE.match(lines[index]):
                insert_at = index
                break
        return _splice(lines, insert_at, section)

    # 2. Before the first ## heading.
    first_level2 = next(
        (i for i, line in enumerate(lines) if _LEVEL2_RE.match(line)), None
    )
    if first_level2 is not None:
        return _splice(lines, first_level2, section)

    # 3. After the title/intro.
    top_title_idx = next(
        (i for i, line in enumerate(lines) if _TOP_TITLE_RE.match(line)), None
    )
    if top_title_idx is not None:
        after = top_title_idx + 1
        while after < len(lines) and not lines[after].strip():
            after += 1
        # Skip non-heading intro lines directly under the title.
        while (
            after < len(lines)
            and lines[after].strip()
            and not lines[after].lstrip().startswith("#")
        ):
            after += 1
        return _splice(lines, after, section)

    # 4. New changelog.
    body = "# Changelog\n\n" + section
    return _ensure_final_newline(body)


def replace_release_section(text: str, version: str, section: str) -> str:
    """Replace an existing release section for ``version`` with ``section``."""
    span = find_release_section(text, version)
    if span is None:
        # Nothing to replace; fall back to insertion.
        return insert_release_section(text, section)
    lines = text.splitlines(keepends=True)
    section = _ensure_final_newline(section)
    new_lines = lines[: span.start] + [section] + lines[span.end :]
    return _ensure_final_newline("".join(new_lines))


def remove_release_section(
    text: str,
    version: str,
    *,
    ignore_missing: bool = False,
) -> str:
    """Remove the changelog section for ``version``.

    Fails unless ``ignore_missing`` is set when the section is absent. Preserves
    all other sections and the final newline. Never invoked by commands that do
    not explicitly remove/cancel/rename a section.
    """
    span = find_release_section(text, version)
    if span is None:
        if ignore_missing:
            return _ensure_final_newline(text)
        raise LaunchError(
            f"Changelog has no section for {version}.",
            code=CODE_NOT_FOUND,
            exit_code=2,
            remediation=["Pass --ignore-missing to skip a missing section."],
        )
    lines = text.splitlines(keepends=True)
    new_lines = lines[: span.start] + lines[span.end :]
    return _collapse_blank_runs(_ensure_final_newline("".join(new_lines)))


def rename_release_section(
    text: str,
    old_version: str,
    new_version: str,
    *,
    ignore_missing: bool = False,
    replace_existing: bool = False,
) -> str:
    """Rename the changelog section heading ``old_version`` to ``new_version``.

    Rewrites only the section heading line; the section body and every other
    section are preserved. Fails unless ``ignore_missing`` when the old section
    is absent, and fails unless ``replace_existing`` when a section for
    ``new_version`` already exists.
    """
    span = find_release_section(text, old_version)
    if span is None:
        if ignore_missing:
            return _ensure_final_newline(text)
        raise LaunchError(
            f"Changelog has no section for {old_version}.",
            code=CODE_NOT_FOUND,
            exit_code=2,
            remediation=["Pass --ignore-missing to skip a missing section."],
        )
    if find_release_section(text, new_version) is not None and not replace_existing:
        raise LaunchError(
            f"Changelog already has a section for {new_version}.",
            code=CODE_CONFLICT,
            exit_code=2,
            remediation=[
                "Pass --replace-existing to overwrite the destination section."
            ],
        )
    lines = text.splitlines(keepends=True)
    heading = lines[span.start]
    escaped = re.escape(old_version)
    new_heading = re.sub(escaped, _literal_replacer(new_version), heading, count=1)
    lines[span.start] = new_heading
    return _ensure_final_newline("".join(lines))


def _splice(lines: list[str], at: int, section: str) -> str:
    """Insert ``section`` at line index ``at``, preserving a blank separator."""
    section = _ensure_final_newline(section)
    # Keep exactly one blank line between the preceding block and the section.
    prefix = lines[:at]
    while prefix and not prefix[-1].strip():
        prefix.pop()
    rebuilt = list(prefix)
    if rebuilt:
        rebuilt.append("\n")
    rebuilt.append(section)
    # Ensure a blank line separates the new section from following content.
    tail = lines[at:]
    rebuilt.append("\n")
    rebuilt.extend(tail)
    return _collapse_blank_runs("".join(rebuilt))


def _collapse_blank_runs(text: str) -> str:
    text = ledgercore.normalize_newlines(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def _resolve_target_file(
    *,
    workspace_root: Path,
    config: ProjectConfig,
    target_file: Path | None,
) -> Path:
    if target_file is not None:
        chosen = str(target_file)
    elif config.changelog_output:
        chosen = config.changelog_output
    else:
        chosen = config.default_changelog or DEFAULT_CHANGELOG
    path = Path(chosen)
    resolved = path if path.is_absolute() else (workspace_root / path)
    return resolved


def _relative_target(workspace_root: Path, target: Path) -> str:
    try:
        return str(target.resolve().relative_to(workspace_root.resolve()))
    except ValueError:
        return str(target)


def _read_target(target: Path) -> str:
    if not target.is_file():
        return ""
    try:
        return target.read_text(encoding="utf-8")
    except OSError as exc:
        raise LaunchError(
            f"Failed to read changelog target {target}: {exc}",
            code=CODE_USAGE_ERROR,
            exit_code=2,
        ) from exc


def build_changelog_file(
    workspace_root: Path,
    *,
    version: str,
    target_file: Path | None = None,
    include_internal: bool = False,
    release_date: str | None = None,
    unreleased: bool = False,
    template_name: str = "default",
    dry_run: bool = False,
    replace_existing: bool = False,
    include_statuses: tuple[str, ...] = ("accepted",),
    strict: bool = False,
    allow_empty: bool = False,
) -> dict[str, object]:
    """Render and optionally update the target changelog for ``version``.

    Dry runs return ``updated=False`` with the rendered ``section``. Non-dry
    runs refuse an existing section for ``version`` unless ``replace_existing``
    is set, then atomically write the merged changelog. Returns a deterministic
    ``changelog_build`` result payload.
    """
    workspace_root = workspace_root.expanduser().resolve()
    paths = resolve_project_paths(workspace_root)
    config = _load_config(paths)
    target = _resolve_target_file(
        workspace_root=workspace_root, config=config, target_file=target_file
    )
    release = load_release(workspace_root, version)
    statuses = tuple(normalize_entry_status(value) for value in include_statuses)
    all_entries = load_entries(workspace_root, version)
    selected = [
        entry
        for entry in all_entries
        if entry.status in statuses and (include_internal or not entry.internal)
    ]
    strict_warnings: list[str] = []
    if strict:
        lint = lint_release_entries(
            workspace_root,
            release_version=version,
            strict=False,
            include_statuses=statuses,
        )
        summary = lint["summary"]
        assert isinstance(summary, dict)
        if int(summary["errors"]) > 0:
            raise LaunchError(
                "Strict build blocked by entry lint errors.",
                code=CODE_VALIDATION_ERROR,
                exit_code=2,
            )
        if not selected and not allow_empty:
            raise LaunchError(
                "Strict build requires at least one included entry; "
                "pass --allow-empty to override.",
                code=CODE_VALIDATION_ERROR,
                exit_code=2,
            )
        release_refs = set(release.source_refs)
        if release.boundary_ref:
            release_refs.add(release.boundary_ref)
        entry_refs = {ref for entry in selected for ref in entry.source_refs}
        uncovered = sorted(release_refs - entry_refs)
        if uncovered and not allow_empty:
            raise LaunchError(
                "Strict build has release source refs not referenced by entries: "
                + ", ".join(uncovered),
                code=CODE_VALIDATION_ERROR,
                exit_code=2,
            )
        if int(summary["warnings"]) > 0:
            strict_warnings.append(
                f"Entry lint reported {summary['warnings']} warning(s)."
            )

    rendered = render_changelog_section(
        workspace_root,
        version=version,
        include_internal=include_internal,
        release_date=release_date,
        unreleased=unreleased,
        template_name=template_name,
        include_statuses=statuses,
    )
    section = str(rendered["section"])
    section_heading = rendered["section_heading"]

    existing = _read_target(target)
    span = find_release_section(existing, version)
    raw_warnings = rendered.get("warnings", [])
    warnings: list[str] = []
    if isinstance(raw_warnings, list):
        warnings = [str(item) for item in raw_warnings]
    warnings.extend(strict_warnings)
    replaced_existing = False

    if dry_run:
        return {
            "kind": "changelog_build",
            "version": version,
            "target_file": _relative_target(workspace_root, target),
            "updated": False,
            "dry_run": True,
            "replaced_existing": bool(span is not None),
            "section": section,
            "section_heading": section_heading,
            "entry_count": rendered["entry_count"],
            "included_internal": bool(include_internal),
            "included_statuses": list(statuses),
            "status_counts": rendered["status_counts"],
            "warnings": warnings,
        }

    if span is not None:
        if not replace_existing:
            raise LaunchError(
                f"Changelog already has a section for {version} in {target}.",
                code=CODE_CONFLICT,
                exit_code=2,
                remediation=[
                    "Re-run with --replace-existing to overwrite the section."
                ],
            )
        merged = replace_release_section(existing, version, section)
        replaced_existing = True
    else:
        merged = insert_release_section(existing, section)

    merged = _ensure_final_newline(merged)
    try:
        ledgercore.ensure_dir(target.parent)
        ledgercore.atomic_write_text(target, merged)
    except (ledgercore.AtomicWriteError, OSError) as exc:
        raise LaunchError(
            f"Failed to write changelog target {target}: {exc}",
            code=CODE_USAGE_ERROR,
            exit_code=2,
        ) from exc

    return {
        "kind": "changelog_build",
        "version": version,
        "target_file": _relative_target(workspace_root, target),
        "updated": True,
        "dry_run": False,
        "replaced_existing": replaced_existing,
        "section_heading": section_heading,
        "entry_count": rendered["entry_count"],
        "included_internal": bool(include_internal),
        "included_statuses": list(statuses),
        "status_counts": rendered["status_counts"],
        "warnings": warnings,
    }


# Silence unused-import analyzers for re-exported Any used only in annotations.
_ = Any
