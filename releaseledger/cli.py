"""Releaseledger command-line interface.

The root :data:`app` exposes ``--cwd``, ``--json`` and ``--version`` and stores
a :class:`~releaseledger.cli_common.CLIState` on the typer context for
subcommands. Subcommand groups are registered progressively (``init``,
``release``, ``entry``, ``changelog``) at the bottom of this module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from releaseledger._version import __version__
from releaseledger.cli_common import (
    CLIState,
    CommandResult,
    cli_state_from_context,
    emit_error,
    emit_payload,
    launch_error_exit_code,
    render_json,
    resolve_workspace_root,
    run_command,
    store_cli_state,
    write_text_output,
)
from releaseledger.errors import ReleaseledgerError
from releaseledger.services.changelog import build_changelog_context
from releaseledger.services.changelog_build import build_changelog_file
from releaseledger.services.config import (
    config_set_releaseledger_dir,
    config_show,
    storage_where,
)
from releaseledger.services.entries import (
    add_many_release_entries,
    add_release_entry,
    import_release_entry_file,
    list_release_entries,
    load_entry_batch_file,
    show_release_entry,
    update_release_entry,
)
from releaseledger.services.entry_lint import lint_release_entries
from releaseledger.services.entry_prompt import build_entry_prompt
from releaseledger.services.releases import (
    UNSET,
    cancel_release,
    check_release_chain,
    create_release,
    finalize_release,
    list_release_records,
    remove_changelog_section,
    rename_changelog_section,
    rename_release,
    repair_release_chain,
    show_release,
    tag_release,
    update_release,
)
from releaseledger.storage.paths import (
    ProjectPaths,
    initialize_project,
    require_project,
)

app = typer.Typer(
    add_completion=True,
    help="Manage project-local release state.",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"releaseledger {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def releaseledger_main(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Print version and exit.",
        ),
    ] = False,
    cwd: Annotated[
        Path | None,
        typer.Option("--cwd", help="Run as if started from PATH."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit JSON envelopes."),
    ] = False,
) -> None:
    """Manage project-local release state."""
    store_cli_state(
        ctx,
        CLIState(cwd=resolve_workspace_root(cwd), json_output=json_output),
    )
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


def _paths(ctx: typer.Context) -> ProjectPaths:
    """Resolve project paths from CLI state, raising on uninitialized projects."""
    state = cli_state_from_context(ctx)
    return require_project(state.cwd)


@app.command("init")
def init_command(
    ctx: typer.Context,
    releaseledger_dir: Annotated[
        str | None,
        typer.Option("--releaseledger-dir", help="State directory name or path."),
    ] = None,
    project_name: Annotated[
        str | None,
        typer.Option("--project-name", help="Project name for changelog headers."),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite an existing config."),
    ] = False,
    external_dir: Annotated[
        bool,
        typer.Option(
            "--external-dir",
            help="Allow --releaseledger-dir to resolve outside the workspace.",
        ),
    ] = False,
) -> None:
    """Initialize .releaseledger.toml and the default state layout."""
    state = cli_state_from_context(ctx)
    workspace_root = state.cwd

    def produce() -> CommandResult:
        result = initialize_project(
            workspace_root,
            releaseledger_dir=releaseledger_dir,
            project_name=project_name,
            force=force,
            external_dir=external_dir,
        )
        rel_dir = Path(str(result["releaseledger_dir"]))
        try:
            display = rel_dir.relative_to(workspace_root.resolve())
            display_str = str(display)
        except ValueError:
            display_str = str(rel_dir)
        human = f"initialized releaseledger in {display_str}\nwrote .releaseledger.toml"
        return result, [], human

    run_command(
        command="init",
        result_type="project_init",
        json_output=state.json_output,
        produce=produce,
    )


release_app = typer.Typer(help="Manage releases.")
app.add_typer(release_app, name="release")


def _release_human_summary(record: dict[str, object]) -> str:
    version = str(record.get("version", ""))
    status = str(record.get("status", ""))
    date_value = record.get("released_at") or record.get("created_at") or ""
    title = record.get("title") or record.get("note") or ""
    title_text = str(title).splitlines()[0] if title else ""
    return f"{version}  {status}  {date_value}  {title_text}".rstrip()


@release_app.command("create")
def release_create_command(
    ctx: typer.Context,
    version: Annotated[str, typer.Argument(help="Release version string.")],
    title: Annotated[str | None, typer.Option("--title", help="Release title.")] = None,
    status: Annotated[
        str,
        typer.Option("--status", help="planned|draft|candidate|released."),
    ] = "planned",
    previous_version: Annotated[
        str | None,
        typer.Option("--previous", help="Explicit previous release version."),
    ] = None,
    note: Annotated[
        str | None, typer.Option("--note", help="Release note body.")
    ] = None,
    changelog_file: Annotated[
        str | None,
        typer.Option("--changelog-file", help="Target changelog file."),
    ] = None,
    released_at: Annotated[
        str | None,
        typer.Option("--released-at", help="Release date YYYY-MM-DD."),
    ] = None,
    boundary_ref: Annotated[
        str | None, typer.Option("--boundary-ref", help="Upper source boundary ref.")
    ] = None,
    source_refs: Annotated[
        list[str] | None,
        typer.Option("--source-ref", help="Included global source ref (repeatable)."),
    ] = None,
    source_count: Annotated[
        int | None, typer.Option("--source-count", help="Number of source records.")
    ] = None,
) -> None:
    """Create a new release record."""
    state = cli_state_from_context(ctx)

    def produce() -> CommandResult:
        workspace_root = _paths(ctx).workspace_root
        result = create_release(
            workspace_root,
            version=version,
            title=title,
            status=status,
            note=note,
            previous_version=previous_version,
            changelog_file=changelog_file,
            released_at=released_at,
            boundary_ref=boundary_ref,
            source_refs=tuple(source_refs or ()),
            source_count=source_count,
        )
        return result, _event_ids(result), f"created release {version}"

    run_command(
        command="release.create",
        result_type="release",
        json_output=state.json_output,
        produce=produce,
    )


@release_app.command("tag")
def release_tag_command(
    ctx: typer.Context,
    version: Annotated[str, typer.Argument(help="Release version string.")],
    previous_version: Annotated[
        str | None,
        typer.Option("--previous", help="Explicit previous release version."),
    ] = None,
    note: Annotated[
        str | None, typer.Option("--note", help="Release note body.")
    ] = None,
    changelog_file: Annotated[
        str | None,
        typer.Option("--changelog-file", help="Target changelog file."),
    ] = None,
    released_at: Annotated[
        str | None,
        typer.Option("--released-at", help="Release date YYYY-MM-DD."),
    ] = None,
    boundary_ref: Annotated[
        str | None, typer.Option("--boundary-ref", help="Upper source boundary ref.")
    ] = None,
    source_refs: Annotated[
        list[str] | None,
        typer.Option("--source-ref", help="Included global source ref (repeatable)."),
    ] = None,
    source_count: Annotated[
        int | None, typer.Option("--source-count", help="Number of source records.")
    ] = None,
) -> None:
    """Create a release with status 'released'."""
    state = cli_state_from_context(ctx)

    def produce() -> CommandResult:
        workspace_root = _paths(ctx).workspace_root
        result = tag_release(
            workspace_root,
            version=version,
            note=note,
            previous_version=previous_version,
            changelog_file=changelog_file,
            released_at=released_at,
            boundary_ref=boundary_ref,
            source_refs=tuple(source_refs or ()),
            source_count=source_count,
        )
        return result, _event_ids(result), f"tagged release {version}"

    run_command(
        command="release.tag",
        result_type="release",
        json_output=state.json_output,
        produce=produce,
    )


@release_app.command("update")
def release_update_command(
    ctx: typer.Context,
    version: Annotated[str, typer.Argument(help="Release version string.")],
    title: Annotated[str | None, typer.Option("--title")] = None,
    status: Annotated[str | None, typer.Option("--status")] = None,
    note: Annotated[str | None, typer.Option("--note")] = None,
    previous_version: Annotated[str | None, typer.Option("--previous")] = None,
    changelog_file: Annotated[str | None, typer.Option("--changelog-file")] = None,
    boundary_ref: Annotated[str | None, typer.Option("--boundary-ref")] = None,
    source_refs: Annotated[list[str] | None, typer.Option("--source-ref")] = None,
    source_count: Annotated[int | None, typer.Option("--source-count")] = None,
    released_at: Annotated[
        str | None,
        typer.Option("--released-at", help="Release date YYYY-MM-DD."),
    ] = None,
    clear_previous: Annotated[
        bool,
        typer.Option("--clear-previous", help="Clear the previous_version field."),
    ] = False,
    clear_changelog_file: Annotated[
        bool,
        typer.Option(
            "--clear-changelog-file", help="Clear the changelog_file field."
        ),
    ] = False,
    clear_boundary_ref: Annotated[
        bool,
        typer.Option("--clear-boundary-ref", help="Clear the boundary_ref field."),
    ] = False,
    clear_source_refs: Annotated[
        bool,
        typer.Option("--clear-source-refs", help="Clear the source_refs field."),
    ] = False,
    clear_source_count: Annotated[
        bool,
        typer.Option("--clear-source-count", help="Clear the source_count field."),
    ] = False,
    clear_released_at: Annotated[
        bool,
        typer.Option("--clear-released-at", help="Clear the released_at field."),
    ] = False,
    force: Annotated[
        bool,
        typer.Option(
            "--force", help="Allow clearing released_at on a released release."
        ),
    ] = False,
) -> None:
    """Update release metadata, with explicit clear flags for optional fields."""
    state = cli_state_from_context(ctx)

    def produce() -> CommandResult:
        result = update_release(
            _paths(ctx).workspace_root,
            version=version,
            title=title,
            status=status,
            note=note,
            previous_version=(
                previous_version if previous_version is not None else UNSET
            ),
            changelog_file=(
                changelog_file if changelog_file is not None else UNSET
            ),
            boundary_ref=boundary_ref if boundary_ref is not None else UNSET,
            source_refs=(
                tuple(source_refs) if source_refs is not None else UNSET
            ),
            source_count=source_count if source_count is not None else UNSET,
            released_at=released_at if released_at is not None else UNSET,
            clear_previous=clear_previous,
            clear_changelog_file=clear_changelog_file,
            clear_boundary_ref=clear_boundary_ref,
            clear_source_refs=clear_source_refs,
            clear_source_count=clear_source_count,
            clear_released_at=clear_released_at,
            force=force,
        )
        return result, _event_ids(result), f"updated release {version}"

    run_command(
        command="release.update",
        result_type="release",
        json_output=state.json_output,
        produce=produce,
    )


@release_app.command("finalize")
def release_finalize_command(
    ctx: typer.Context,
    version: Annotated[str, typer.Argument(help="Release version string.")],
    released_at: Annotated[
        str | None,
        typer.Option("--released-at", help="Release date YYYY-MM-DD."),
    ] = None,
    changelog_file: Annotated[
        str | None,
        typer.Option("--changelog-file", help="Target changelog file."),
    ] = None,
) -> None:
    """Transition a planned/draft/candidate release to 'released'."""
    state = cli_state_from_context(ctx)

    def produce() -> CommandResult:
        workspace_root = _paths(ctx).workspace_root
        result = finalize_release(
            workspace_root,
            version=version,
            released_at=released_at,
            changelog_file=changelog_file,
        )
        return result, _event_ids(result), f"finalized release {version}"

    run_command(
        command="release.finalize",
        result_type="release",
        json_output=state.json_output,
        produce=produce,
    )


@release_app.command("list")
def release_list_command(ctx: typer.Context) -> None:
    """List all releases."""
    state = cli_state_from_context(ctx)

    def produce() -> CommandResult:
        workspace_root = _paths(ctx).workspace_root
        releases = list_release_records(workspace_root)
        result: dict[str, object] = {"kind": "release_list", "releases": releases}
        if releases:
            lines = ["RELEASES"]
            for record in releases:
                lines.append(_release_human_summary(record))
            human = "\n".join(lines)
        else:
            human = "RELEASES\n(none)"
        return result, [], human

    run_command(
        command="release.list",
        result_type="release_list",
        json_output=state.json_output,
        produce=produce,
    )


@release_app.command("show")
def release_show_command(
    ctx: typer.Context,
    version: Annotated[str, typer.Argument(help="Release version string.")],
) -> None:
    """Show a release and its entries."""
    state = cli_state_from_context(ctx)

    def produce() -> CommandResult:
        workspace_root = _paths(ctx).workspace_root
        result = show_release(workspace_root, version)
        release_raw = result.get("release", {})
        record = dict(release_raw) if isinstance(release_raw, dict) else {}
        lines = [f"version: {record.get('version', '')}"]
        lines.append(f"status: {record.get('status', '')}")
        if record.get("title"):
            lines.append(f"title: {record['title']}")
        if record.get("released_at"):
            lines.append(f"released_at: {record['released_at']}")
        if record.get("previous_version"):
            lines.append(f"previous_version: {record['previous_version']}")
        lines.append(f"entry_count: {result.get('entry_count', 0)}")
        note = record.get("note")
        if note:
            note_text = str(note).splitlines()[0] if str(note).splitlines() else ""
            if note_text:
                lines.append(f"note: {note_text}")
        human = "\n".join(lines)
        return result, [], human

    run_command(
        command="release.show",
        result_type="release",
        json_output=state.json_output,
        produce=produce,
    )


@release_app.command("cancel")
def release_cancel_command(
    ctx: typer.Context,
    version: Annotated[str, typer.Argument(help="Release version to cancel.")],
    reason: Annotated[
        str | None,
        typer.Option("--reason", help="Why the release was canceled."),
    ] = None,
    superseded_by: Annotated[
        str | None,
        typer.Option("--superseded-by", help="Release version that replaces this one."),
    ] = None,
    force_released_unshipped: Annotated[
        bool,
        typer.Option(
            "--force-released-unshipped",
            help="Allow canceling a release currently marked 'released'.",
        ),
    ] = False,
    canceled_at: Annotated[
        str | None,
        typer.Option("--canceled-at", help="Cancellation date YYYY-MM-DD."),
    ] = None,
    target_file: Annotated[
        Path | None,
        typer.Option("--target-file", help="Changelog file to update."),
    ] = None,
    remove_changelog_section: Annotated[
        bool,
        typer.Option(
            "--remove-changelog-section",
            help="Remove the release section from the changelog file.",
        ),
    ] = False,
    ignore_missing_section: Annotated[
        bool,
        typer.Option("--ignore-missing", help="Skip a missing changelog section."),
    ] = False,
) -> None:
    """Mark a release as canceled (never shipped)."""
    state = cli_state_from_context(ctx)

    def produce() -> CommandResult:
        result = cancel_release(
            _paths(ctx).workspace_root,
            version=version,
            reason=reason,
            superseded_by=superseded_by,
            force_released_unshipped=force_released_unshipped,
            canceled_at=canceled_at,
            target_file=target_file,
            remove_changelog_section=remove_changelog_section,
            ignore_missing_section=ignore_missing_section,
        )
        return result, _event_ids(result), f"canceled release {version}"

    run_command(
        command="release.cancel",
        result_type="release",
        json_output=state.json_output,
        produce=produce,
    )


@release_app.command("rename")
def release_rename_command(
    ctx: typer.Context,
    old_version: Annotated[str, typer.Argument(help="Release version to rename.")],
    new_version: Annotated[
        str, typer.Argument(help="New release version string.")
    ],
    previous_version: Annotated[
        str | None,
        typer.Option(
            "--previous", help="Override previous_version for the renamed release."
        ),
    ] = None,
    title: Annotated[
        str | None,
        typer.Option("--title", help="Override the release title."),
    ] = None,
    released_at: Annotated[
        str | None,
        typer.Option("--released-at", help="Release date YYYY-MM-DD."),
    ] = None,
    force_released_unshipped: Annotated[
        bool,
        typer.Option(
            "--force-released-unshipped",
            help="Allow renaming a release currently marked 'released'.",
        ),
    ] = False,
    rewrite_successors: Annotated[
        bool,
        typer.Option(
            "--rewrite-successors",
            help="Update releases whose previous_version points at the old version.",
        ),
    ] = False,
    target_file: Annotated[
        Path | None,
        typer.Option("--target-file", help="Changelog file to update."),
    ] = None,
    rename_changelog_section: Annotated[
        bool,
        typer.Option(
            "--rename-changelog-section",
            help="Rename the changelog section heading to the new version.",
        ),
    ] = False,
    replace_existing_section: Annotated[
        bool,
        typer.Option(
            "--replace-existing-section",
            help="Overwrite a destination changelog section if it exists.",
        ),
    ] = False,
) -> None:
    """Rename a release and move its bundle to the new version."""
    state = cli_state_from_context(ctx)

    def produce() -> CommandResult:
        result = rename_release(
            _paths(ctx).workspace_root,
            old_version=old_version,
            new_version=new_version,
            previous_version=(
                previous_version if previous_version is not None else UNSET
            ),
            title=title,
            released_at=released_at if released_at is not None else UNSET,
            force_released_unshipped=force_released_unshipped,
            rewrite_successors=rewrite_successors,
            target_file=target_file,
            rename_changelog_section=rename_changelog_section,
            replace_existing_section=replace_existing_section,
        )
        return (
            result,
            _event_ids(result),
            f"renamed release {old_version} to {new_version}",
        )

    run_command(
        command="release.rename",
        result_type="release",
        json_output=state.json_output,
        produce=produce,
    )


chain_app = typer.Typer(help="Inspect and repair the release predecessor chain.")
release_app.add_typer(chain_app, name="chain")


@chain_app.command("check")
def release_chain_check_command(ctx: typer.Context) -> None:
    """Report problems in the release predecessor chain."""
    state = cli_state_from_context(ctx)

    def produce() -> CommandResult:
        result = check_release_chain(_paths(ctx).workspace_root)
        problems = result.get("problems", [])
        if problems:
            lines = ["CHAIN PROBLEMS"]
            for problem in problems:
                assert isinstance(problem, dict)
                lines.append(
                    f"{problem.get('version')}  {problem.get('kind')}"
                    f"  -> {problem.get('previous_version')}"
                )
            human = "\n".join(lines)
        else:
            human = "CHAIN OK"
        return result, [], human

    run_command(
        command="release.chain.check",
        result_type="release_chain_check",
        json_output=state.json_output,
        produce=produce,
    )


@chain_app.command("repair")
def release_chain_repair_command(
    ctx: typer.Context,
    apply_changes: Annotated[
        bool,
        typer.Option("--apply", help="Write the computed chain fixes."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview chain fixes without writing."),
    ] = False,
) -> None:
    """Recompute predecessor links from release order (dry-run or --apply)."""
    state = cli_state_from_context(ctx)
    should_apply = apply_changes and not dry_run

    def produce() -> CommandResult:
        result = repair_release_chain(
            _paths(ctx).workspace_root, apply_changes=should_apply
        )
        changes = result.get("changes", [])
        if changes:
            lines = ["CHAIN CHANGES" + (" (applied)" if should_apply else " (dry-run)")]
            for change in changes:
                assert isinstance(change, dict)
                lines.append(
                    f"{change.get('version')}  {change.get('from')}"
                    f"  ->  {change.get('to')}"
                )
            human = "\n".join(lines)
        else:
            human = "CHAIN OK (no changes)"
        return result, _event_ids(result), human

    run_command(
        command="release.chain.repair",
        result_type="release_chain_repair",
        json_output=state.json_output,
        produce=produce,
    )


def _event_ids(result: dict[str, object]) -> list[str]:
    events = result.get("events")
    if isinstance(events, list):
        return [str(item) for item in events]
    return []


entry_app = typer.Typer(help="Manage release entries.")
app.add_typer(entry_app, name="entry")


@entry_app.command("add")
def entry_add_command(
    ctx: typer.Context,
    version: Annotated[str, typer.Argument(help="Release version string.")],
    kind: Annotated[str, typer.Option("--kind", help="Entry kind.")] = "added",
    summary: Annotated[
        str,
        typer.Option("--summary", help="One-line change summary."),
    ] = "",
    body: Annotated[
        str | None,
        typer.Option("--body", help="Optional longer entry details."),
    ] = None,
    paths: Annotated[
        list[str] | None,
        typer.Option("--path", help="Relative path affected (repeatable)."),
    ] = None,
    issues: Annotated[
        list[str] | None,
        typer.Option("--issue", help="Issue reference (repeatable)."),
    ] = None,
    prs: Annotated[
        list[str] | None,
        typer.Option("--pr", help="Pull request reference (repeatable)."),
    ] = None,
    sources: Annotated[
        list[str] | None,
        typer.Option("--source", help="Provenance source reference (repeatable)."),
    ] = None,
    status: Annotated[
        str, typer.Option("--status", help="draft|accepted|rejected.")
    ] = "accepted",
    audience: Annotated[str | None, typer.Option("--audience")] = None,
    scopes: Annotated[
        list[str] | None, typer.Option("--scope", help="Entry scope (repeatable).")
    ] = None,
    source_refs: Annotated[
        list[str] | None,
        typer.Option("--source-ref", help="Global source ref (repeatable)."),
    ] = None,
    breaking: Annotated[
        bool,
        typer.Option("--breaking", help="Mark as a breaking change."),
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Validate without writing.")
    ] = False,
    internal: Annotated[
        bool,
        typer.Option("--internal", help="Hide from default changelog output."),
    ] = False,
) -> None:
    """Add a changelog entry to a release."""
    state = cli_state_from_context(ctx)

    def produce() -> CommandResult:
        workspace_root = _paths(ctx).workspace_root
        result = add_release_entry(
            workspace_root,
            release_version=version,
            kind=kind,
            summary=summary,
            body=body,
            paths=tuple(paths or ()),
            issues=tuple(issues or ()),
            prs=tuple(prs or ()),
            sources=tuple(sources or ()),
            status=status,
            audience=audience,
            scopes=tuple(scopes or ()),
            source_refs=tuple(source_refs or ()),
            breaking=breaking,
            internal=internal,
            dry_run=dry_run,
        )
        entry_raw = result.get("entry", {})
        entry = dict(entry_raw) if isinstance(entry_raw, dict) else {}
        entry_id = str(entry.get("entry_id", ""))
        human = (
            f"previewed entry {entry_id} for release {version}"
            if dry_run
            else f"added entry {entry_id} to release {version}"
        )
        return result, _event_ids(result), human

    run_command(
        command="entry.add",
        result_type="release_entry",
        json_output=state.json_output,
        produce=produce,
    )


@entry_app.command("show")
def entry_show_command(
    ctx: typer.Context,
    version: Annotated[str, typer.Argument()],
    entry_id: Annotated[str, typer.Argument()],
) -> None:
    """Show one release entry."""
    state = cli_state_from_context(ctx)

    def produce() -> CommandResult:
        result = show_release_entry(_paths(ctx).workspace_root, version, entry_id)
        entry = result["entry"]
        assert isinstance(entry, dict)
        return result, [], f"{entry_id}  {entry['kind']}  {entry['summary']}"

    run_command(
        command="entry.show",
        result_type="release_entry",
        json_output=state.json_output,
        produce=produce,
    )


@entry_app.command("update")
def entry_update_command(
    ctx: typer.Context,
    version: Annotated[str, typer.Argument()],
    entry_id: Annotated[str, typer.Argument()],
    kind: Annotated[str | None, typer.Option("--kind")] = None,
    summary: Annotated[str | None, typer.Option("--summary")] = None,
    body: Annotated[str | None, typer.Option("--body")] = None,
    status: Annotated[str | None, typer.Option("--status")] = None,
    audience: Annotated[str | None, typer.Option("--audience")] = None,
    scopes: Annotated[list[str] | None, typer.Option("--scope")] = None,
    source_refs: Annotated[list[str] | None, typer.Option("--source-ref")] = None,
    paths: Annotated[list[str] | None, typer.Option("--path")] = None,
    issues: Annotated[list[str] | None, typer.Option("--issue")] = None,
    prs: Annotated[list[str] | None, typer.Option("--pr")] = None,
    breaking: Annotated[bool | None, typer.Option("--breaking/--no-breaking")] = None,
    internal: Annotated[bool | None, typer.Option("--internal/--no-internal")] = None,
) -> None:
    """Update explicitly supplied entry fields."""
    state = cli_state_from_context(ctx)

    def produce() -> CommandResult:
        result = update_release_entry(
            _paths(ctx).workspace_root,
            release_version=version,
            entry_id=entry_id,
            kind=kind,
            summary=summary,
            body=body,
            status=status,
            audience=audience,
            scopes=tuple(scopes) if scopes is not None else None,
            source_refs=(tuple(source_refs) if source_refs is not None else None),
            paths=tuple(paths) if paths is not None else None,
            issues=tuple(issues) if issues is not None else None,
            prs=tuple(prs) if prs is not None else None,
            breaking=breaking,
            internal=internal,
        )
        return result, _event_ids(result), f"updated entry {entry_id}"

    run_command(
        command="entry.update",
        result_type="release_entry",
        json_output=state.json_output,
        produce=produce,
    )


@entry_app.command("import")
def entry_import_command(
    ctx: typer.Context,
    version: Annotated[str, typer.Argument()],
    source_path: Annotated[Path, typer.Option("--file")],
    replace_existing: Annotated[bool, typer.Option("--replace")] = False,
    source_ledger: Annotated[str | None, typer.Option("--source-ledger")] = None,
) -> None:
    """Import a releaseledger or legacy taskledger entry document."""
    state = cli_state_from_context(ctx)

    def produce() -> CommandResult:
        result = import_release_entry_file(
            _paths(ctx).workspace_root,
            release_version=version,
            source_path=source_path,
            replace_existing=replace_existing,
            source_ledger=source_ledger,
        )
        entry = result["entry"]
        assert isinstance(entry, dict)
        entry_id = str(entry["entry_id"])
        return result, _event_ids(result), f"imported entry {entry_id}"

    run_command(
        command="entry.import",
        result_type="release_entry",
        json_output=state.json_output,
        produce=produce,
    )


@entry_app.command("add-many")
def entry_add_many_command(
    ctx: typer.Context,
    version: Annotated[str, typer.Argument()],
    source_path: Annotated[Path, typer.Option("--file")],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Add a validated YAML batch atomically."""
    state = cli_state_from_context(ctx)

    def produce() -> CommandResult:
        entries = load_entry_batch_file(source_path)
        result = add_many_release_entries(
            _paths(ctx).workspace_root,
            release_version=version,
            entries=entries,
            dry_run=dry_run,
        )
        issues = result.get("issues")
        if isinstance(issues, list) and issues:
            raise ReleaseledgerError(
                f"Entry batch validation failed with {len(issues)} issue(s).",
                code="VALIDATION_ERROR",
                exit_code=2,
            )
        action = "previewed" if dry_run else "added"
        return (
            result,
            _event_ids(result),
            f"{action} {len(entries)} entries for release {version}",
        )

    run_command(
        command="entry.add-many",
        result_type="release_entry_batch",
        json_output=state.json_output,
        produce=produce,
    )


@entry_app.command("list")
def entry_list_command(
    ctx: typer.Context,
    version: Annotated[str, typer.Argument(help="Release version string.")],
) -> None:
    """List entries for a release."""
    state = cli_state_from_context(ctx)

    def produce() -> CommandResult:
        workspace_root = _paths(ctx).workspace_root
        entries = list_release_entries(workspace_root, version)
        result: dict[str, object] = {
            "kind": "release_entry_list",
            "release_version": version,
            "entries": entries,
        }
        if entries:
            lines = ["ENTRIES"]
            for entry in entries:
                eid = str(entry.get("entry_id", ""))
                k = str(entry.get("kind", ""))
                s = str(entry.get("summary", ""))
                lines.append(f"{eid}  {k}  {s}")
            human = "\n".join(lines)
        else:
            human = "ENTRIES\n(none)"
        return result, [], human

    run_command(
        command="entry.list",
        result_type="release_entry_list",
        json_output=state.json_output,
        produce=produce,
    )


@entry_app.command("lint")
def entry_lint_command(
    ctx: typer.Context,
    version: Annotated[str, typer.Argument()],
    strict: Annotated[bool, typer.Option("--strict")] = False,
    include_statuses: Annotated[
        list[str] | None, typer.Option("--include-status")
    ] = None,
) -> None:
    """Lint release entries and optionally fail on warnings."""
    state = cli_state_from_context(ctx)

    def produce() -> CommandResult:
        result = lint_release_entries(
            _paths(ctx).workspace_root,
            release_version=version,
            strict=strict,
            include_statuses=(
                tuple(include_statuses) if include_statuses is not None else None
            ),
        )
        if not result["passed"]:
            summary = result["summary"]
            assert isinstance(summary, dict)
            raise ReleaseledgerError(
                f"Entry lint failed with {summary['errors']} error(s) and "
                f"{summary['warnings']} warning(s).",
                code="VALIDATION_ERROR",
                exit_code=2,
            )
        summary = result["summary"]
        assert isinstance(summary, dict)
        human = (
            f"entry lint passed: {summary['errors']} error(s), "
            f"{summary['warnings']} warning(s)"
        )
        return result, [], human

    run_command(
        command="entry.lint",
        result_type="entry_lint",
        json_output=state.json_output,
        produce=produce,
    )


@entry_app.command("prompt")
def entry_prompt_command(
    ctx: typer.Context,
    version: Annotated[str, typer.Argument()],
    source_refs: Annotated[list[str] | None, typer.Option("--source-ref")] = None,
    context_file: Annotated[Path | None, typer.Option("--context-file")] = None,
    format_name: Annotated[str, typer.Option("--format")] = "markdown",
    output: Annotated[Path | None, typer.Option("--output")] = None,
) -> None:
    """Render a prompt for drafting release entries."""
    state = cli_state_from_context(ctx)
    try:
        result = build_entry_prompt(
            _paths(ctx).workspace_root,
            release_version=version,
            source_refs=tuple(source_refs or ()),
            context_file=context_file,
            format_name=format_name,
        )
    except ReleaseledgerError as exc:
        emit_error(command="entry.prompt", error=exc, json_output=state.json_output)
        raise typer.Exit(launch_error_exit_code(exc)) from exc
    text = render_json(result) if isinstance(result, dict) else result
    if output is not None:
        target = write_text_output(output, text)
        if state.json_output:
            typer.echo(
                render_json(
                    {
                        "ok": True,
                        "command": "entry.prompt",
                        "result_type": "entry_prompt",
                        "result": {"output": str(target), "format": format_name},
                    }
                )
            )
        else:
            typer.echo(f"wrote {target}")
        return
    typer.echo(text)


@app.command("changelog")
def changelog_command(
    ctx: typer.Context,
    version: Annotated[str, typer.Argument(help="Release version string.")],
    format_name: Annotated[
        str,
        typer.Option("--format", help="Output format: markdown or json."),
    ] = "markdown",
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Write rendered content to PATH."),
    ] = None,
    include_internal: Annotated[
        bool,
        typer.Option("--include-internal", help="Include internal entries."),
    ] = False,
    target_changelog: Annotated[
        str | None,
        typer.Option("--target-changelog", help="Target changelog file."),
    ] = None,
    release_date: Annotated[
        str | None,
        typer.Option("--release-date", help="Release date YYYY-MM-DD."),
    ] = None,
    include_sources: Annotated[
        bool,
        typer.Option(
            "--include-sources", help="Show provenance sources in markdown output."
        ),
    ] = False,
    include_statuses: Annotated[
        list[str] | None, typer.Option("--include-status")
    ] = None,
    lint: Annotated[bool, typer.Option("--lint")] = False,
) -> None:
    """Render changelog context for a release."""
    state = cli_state_from_context(ctx)
    if format_name not in {"markdown", "json"}:
        err = ReleaseledgerError(
            f"Unsupported --format: {format_name!r}",
            code="USAGE_ERROR",
            exit_code=2,
        )
        emit_error(command="changelog", error=err, json_output=state.json_output)
        raise typer.Exit(launch_error_exit_code(err)) from err
    try:
        workspace_root = _paths(ctx).workspace_root
        content = build_changelog_context(
            workspace_root,
            version=version,
            format_name=format_name,
            include_internal=include_internal,
            include_sources=include_sources,
            target_changelog=target_changelog,
            release_date=release_date,
            include_statuses=tuple(include_statuses or ("accepted",)),
            lint=lint,
        )
    except ReleaseledgerError as exc:
        emit_error(command="changelog", error=exc, json_output=state.json_output)
        raise typer.Exit(launch_error_exit_code(exc)) from exc
    if format_name == "json":
        text = render_json(content) if isinstance(content, dict) else str(content)
    else:
        text = content if isinstance(content, str) else render_json(content)
    if output is not None:
        out_path = write_text_output(output, text)
        if state.json_output:
            payload: dict[str, object] = {
                "ok": True,
                "command": "changelog",
                "result_type": "changelog",
                "result": {"output": str(out_path), "format": format_name},
            }
            typer.echo(render_json(payload))
        else:
            typer.echo(f"wrote {out_path}")
        return
    typer.echo(text)


@app.command("build")
def build_command(
    ctx: typer.Context,
    version: Annotated[str, typer.Argument(help="Release version string.")],
    target_file: Annotated[
        Path | None,
        typer.Option("--target-file", help="CHANGELOG target file."),
    ] = None,
    release_date: Annotated[
        str | None,
        typer.Option("--release-date", help="Release date YYYY-MM-DD."),
    ] = None,
    unreleased: Annotated[
        bool,
        typer.Option("--unreleased", help="Render the date as Unreleased/no date."),
    ] = False,
    include_internal: Annotated[
        bool,
        typer.Option("--include-internal", help="Include internal entries."),
    ] = False,
    template: Annotated[
        str,
        typer.Option("--template", help="Named template profile."),
    ] = "default",
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print rendered section; do not write."),
    ] = False,
    replace_existing: Annotated[
        bool,
        typer.Option(
            "--replace-existing",
            help="Replace an existing section for VERSION.",
        ),
    ] = False,
    format_name: Annotated[
        str,
        typer.Option("--format", help="Output format: markdown or json."),
    ] = "markdown",
    include_statuses: Annotated[
        list[str] | None, typer.Option("--include-status")
    ] = None,
    strict: Annotated[bool, typer.Option("--strict")] = False,
    allow_empty: Annotated[bool, typer.Option("--allow-empty")] = False,
) -> None:
    """Build or update CHANGELOG.md for a release."""
    state = cli_state_from_context(ctx)
    if format_name not in {"markdown", "json"}:
        err = ReleaseledgerError(
            f"Unsupported --format: {format_name!r}",
            code="USAGE_ERROR",
            exit_code=2,
        )
        emit_error(command="build", error=err, json_output=state.json_output)
        raise typer.Exit(launch_error_exit_code(err)) from err
    try:
        workspace_root = _paths(ctx).workspace_root
        result = build_changelog_file(
            workspace_root,
            version=version,
            target_file=target_file,
            include_internal=include_internal,
            release_date=release_date,
            unreleased=unreleased,
            template_name=template,
            dry_run=dry_run,
            replace_existing=replace_existing,
            include_statuses=tuple(include_statuses or ("accepted",)),
            strict=strict,
            allow_empty=allow_empty,
        )
    except ReleaseledgerError as exc:
        emit_error(command="build", error=exc, json_output=state.json_output)
        raise typer.Exit(launch_error_exit_code(exc)) from exc
    target = str(result.get("target_file", ""))
    if dry_run:
        human = str(result.get("section", ""))
    else:
        human = f"wrote {target}"
    emit_payload(
        command="build",
        result_type="changelog_build",
        result=result,
        human=human,
        json_output=state.json_output,
    )



changelog_section_app = typer.Typer(
    help="Correct release sections in an existing changelog file."
)
app.add_typer(changelog_section_app, name="changelog-section")


@changelog_section_app.command("remove-section")
def changelog_remove_section_command(
    ctx: typer.Context,
    version: Annotated[str, typer.Argument(help="Release section to remove.")],
    target_file: Annotated[
        Path,
        typer.Option("--target-file", help="Changelog file to update."),
    ],
    ignore_missing: Annotated[
        bool,
        typer.Option("--ignore-missing", help="Skip a missing section."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview without writing."),
    ] = False,
) -> None:
    """Remove a release section from a changelog file."""
    state = cli_state_from_context(ctx)

    def produce() -> CommandResult:
        result = remove_changelog_section(
            _paths(ctx).workspace_root,
            version=version,
            target_file=target_file,
            ignore_missing=ignore_missing,
            dry_run=dry_run,
        )
        human = (
            f"previewed removal of section {version}"
            if dry_run
            else f"removed section {version}"
        )
        return result, [], human

    run_command(
        command="changelog-section.remove",
        result_type="changelog_section_remove",
        json_output=state.json_output,
        produce=produce,
    )


@changelog_section_app.command("rename-section")
def changelog_rename_section_command(
    ctx: typer.Context,
    old_version: Annotated[str, typer.Argument(help="Section version to rename.")],
    new_version: Annotated[str, typer.Argument(help="New section version.")],
    target_file: Annotated[
        Path,
        typer.Option("--target-file", help="Changelog file to update."),
    ],
    ignore_missing: Annotated[
        bool,
        typer.Option("--ignore-missing", help="Skip a missing source section."),
    ] = False,
    replace_existing: Annotated[
        bool,
        typer.Option(
            "--replace-existing", help="Overwrite an existing destination section."
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview without writing."),
    ] = False,
) -> None:
    """Rename a release section heading in a changelog file."""
    state = cli_state_from_context(ctx)

    def produce() -> CommandResult:
        result = rename_changelog_section(
            _paths(ctx).workspace_root,
            old_version=old_version,
            new_version=new_version,
            target_file=target_file,
            ignore_missing=ignore_missing,
            replace_existing=replace_existing,
            dry_run=dry_run,
        )
        human = (
            f"previewed rename of section {old_version} to {new_version}"
            if dry_run
            else f"renamed section {old_version} to {new_version}"
        )
        return result, [], human

    run_command(
        command="changelog-section.rename",
        result_type="changelog_section_rename",
        json_output=state.json_output,
        produce=produce,
    )

storage_app = typer.Typer(help="Storage diagnostics.")
app.add_typer(storage_app, name="storage")


@storage_app.command("where")
def storage_where_command(ctx: typer.Context) -> None:
    """Show the effective storage location, layout health, and config source."""
    state = cli_state_from_context(ctx)

    def produce() -> CommandResult:
        result = storage_where(state.cwd)
        # Build human output
        inside = "yes" if result.get("inside_workspace") else "no"
        layout = "ok" if result.get("layout_exists") else "missing"
        indexes = "ok" if result.get("indexes_exist") else "missing"
        lines = [
            f"Workspace: {result.get('workspace_root', '')}",
            f"Config: {result.get('config_path', '')}",
            f"Storage: {result.get('releaseledger_dir', '')}",
            f"Ledger: {result.get('ledger_ref', '')}",
            f"Inside workspace: {inside}",
            f"Source: {result.get('source', '')}",
            f"Layout: {layout}",
            f"Indexes: {indexes}",
        ]
        human = "\n".join(lines)
        return result, [], human

    run_command(
        command="storage.where",
        result_type="storage_location",
        json_output=state.json_output,
        produce=produce,
    )


config_app = typer.Typer(help="Config management.")
app.add_typer(config_app, name="config")


@config_app.command("show")
def config_show_command(ctx: typer.Context) -> None:
    """Show the validated project configuration and resolved paths."""
    state = cli_state_from_context(ctx)

    def produce() -> CommandResult:
        result = config_show(state.cwd)
        cfg = result.get("config", {})
        if not isinstance(cfg, dict):
            cfg = {}
        lines = [
            f"Workspace: {result.get('workspace_root', '')}",
            f"Config: {result.get('config_path', '')}",
            f"Storage: {result.get('releaseledger_dir', '')}",
            f"Policy: {cfg.get('releaseledger_dir_policy', 'workspace')}",
            f"Ledger ref: {cfg.get('ledger_ref', '')}",
        ]
        human = "\n".join(lines)
        return result, [], human

    run_command(
        command="config.show",
        result_type="config_show",
        json_output=state.json_output,
        produce=produce,
    )


@config_app.command("set")
def config_set_command(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Config key to set.")],
    value: Annotated[str, typer.Argument(help="New value.")],
    external_dir: Annotated[
        bool,
        typer.Option(
            "--external-dir",
            help="Allow releaseledger_dir to resolve outside the workspace.",
        ),
    ] = False,
) -> None:
    """Atomically set a config key in .releaseledger.toml."""
    state = cli_state_from_context(ctx)
    if key != "releaseledger_dir":
        err = ReleaseledgerError(
            f"Unsupported config key: {key!r}."
            " Only 'releaseledger_dir' is currently supported.",
            code="USAGE_ERROR",
            exit_code=2,
        )
        emit_error(command="config.set", error=err, json_output=state.json_output)
        raise typer.Exit(launch_error_exit_code(err)) from err

    def produce() -> CommandResult:
        result = config_set_releaseledger_dir(
            state.cwd, value, external_dir=external_dir
        )
        human = f"set releaseledger_dir: {result['before']} -> {result['after']}"
        return result, [], human

    run_command(
        command="config.set",
        result_type="config_set",
        json_output=state.json_output,
        produce=produce,
    )
