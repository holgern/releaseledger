# releaseledger

Project-local release management for coding workflows.

`releaseledger` is a standalone, branch-scoped release-state ledger. It tracks
releases, changelog entries, events, and indexes under a `.releaseledger/`
directory configured by `.releaseledger.toml`. It reuses primitives from
[`ledgercore`](https://github.com/holgern/ledgercore) and does **not** depend on
`taskledger`.

- Release records are stored as Markdown-with-front-matter bundles:
  `.releaseledger/ledgers/<ledger_ref>/releases/<version>/release.md`.
- Changelog entries live alongside: `releases/<version>/entries/entry-NNNN.md`.
- Every mutation appends a JSONL event and rebuilds JSON indexes.
- `--json` envelopes are deterministic (sorted keys, trailing newline).

## Quickstart

```bash
releaseledger init
releaseledger release create 1.2.0 --title "Release 1.2.0" \
  --boundary-ref tl:task-0105 --source-ref tl:task-0103
releaseledger entry add 1.2.0 --kind added \
  --summary "Added release bundle storage" --status accepted \
  --source-ref tl:task-0103
releaseledger entry lint 1.2.0 --strict
releaseledger changelog 1.2.0 --target-changelog CHANGELOG.md --release-date 2026-06-13
releaseledger build 1.2.0 --dry-run --strict --target-file CHANGELOG.md
```

`changelog` produces source/context for review or drafting; `build` writes the
final `CHANGELOG.md` section. Build CHANGELOG.md:

```bash
releaseledger changelog 1.2.0 --format json
releaseledger build 1.2.0 --dry-run --target-file CHANGELOG.md
releaseledger build 1.2.0 --release-date 2026-06-13 --target-file CHANGELOG.md
```

After `init` you get a `.releaseledger.toml` and a `.releaseledger/` layout:

```text
.releaseledger/
  ledgers/
    main/
      releases/      # one bundle per version (release.md + entries/)
      events/        # events.jsonl audit log
      indexes/       # releases.json, entries.json
```

## Commands

```text
releaseledger init [--releaseledger-dir .releaseledger] [--project-name NAME]
                  [--external-dir] [--force]
releaseledger release create VERSION [--title TEXT] [--status planned|draft|candidate|released]
                                     [--previous VERSION] [--note TEXT] [--changelog-file PATH]
                                     [--released-at YYYY-MM-DD] [--boundary-ref REF]
                                     [--source-ref REF]... [--source-count N]
releaseledger release update VERSION [--title TEXT] [--status STATUS] [--previous VERSION]
                                     [--note TEXT] [--changelog-file PATH]
                                     [--boundary-ref REF] [--source-ref REF]... [--source-count N]
releaseledger release tag VERSION [--previous VERSION] [--note TEXT] [--changelog-file PATH]
                                  [--released-at YYYY-MM-DD] [--boundary-ref REF]
                                  [--source-ref REF]... [--source-count N]
releaseledger release finalize VERSION [--released-at YYYY-MM-DD] [--changelog-file PATH]
releaseledger release list
releaseledger release show VERSION
releaseledger entry add VERSION --kind KIND --summary TEXT [--body TEXT]
                               [--status draft|accepted|rejected] [--audience TEXT]
                               [--scope SCOPE]... [--source-ref REF]... [--dry-run]
                               [--path PATH]... [--issue REF]... [--pr REF]...
                               [--breaking] [--internal]
releaseledger entry add-many VERSION --file FILE [--dry-run]
releaseledger entry update VERSION ENTRY_ID [entry field options]
releaseledger entry show VERSION ENTRY_ID
releaseledger entry import VERSION --file FILE [--replace] [--source-ledger LEDGER]
releaseledger entry list VERSION
releaseledger entry lint VERSION [--strict] [--include-status STATUS]...
releaseledger entry prompt VERSION [--source-ref REF]... [--context-file FILE]
                                   [--format markdown|json] [--output PATH]
releaseledger changelog VERSION [--format markdown|json] [--output PATH]
                                [--include-internal] [--target-changelog PATH]
                                [--release-date YYYY-MM-DD]
                                [--include-status STATUS]... [--lint]
releaseledger build VERSION [--target-file CHANGELOG.md] [--release-date YYYY-MM-DD]
                            [--unreleased] [--include-internal] [--dry-run]
                            [--replace-existing] [--format markdown|json]
                            [--include-status STATUS]... [--strict] [--allow-empty]
releaseledger storage where
releaseledger config show
releaseledger config set releaseledger_dir PATH [--external-dir]
```

Entry kinds: `added`, `changed`, `fixed`, `removed`, `deprecated`, `security`,
`docs`, `quality`, `internal`. `documentation` and `doc` are accepted aliases
for canonical `docs`. Entry statuses are `draft`, `accepted`, and `rejected`;
builds include only accepted entries by default.

## Cross-ledger provenance

Releaseledger remains standalone. It never imports taskledger, reads
`.taskledger/`, or validates external task state. Link externally gathered
evidence with canonical global refs:

```bash
taskledger task show task-0103 --json > /tmp/task-0103.json
releaseledger entry prompt 1.2.0 --source-ref tl:task-0103 \
  --context-file /tmp/task-0103.json --output /tmp/entry-prompt.md
releaseledger entry add-many 1.2.0 --file /tmp/1.2.0-entries.yaml --dry-run
releaseledger entry add-many 1.2.0 --file /tmp/1.2.0-entries.yaml
releaseledger entry lint 1.2.0 --strict
releaseledger build 1.2.0 --dry-run --strict --target-file CHANGELOG.md
```

Root options: `--cwd PATH` (run as if started from `PATH`; the project is
discovered upward), `--json` (emit JSON envelopes), `--version`.

## JSON envelopes

Success:

```json
{
  "ok": true,
  "command": "release.tag",
  "result_type": "release",
  "result": {
    "kind": "release",
    "ledger_ref": "main",
    "release": { "version": "1.2.0", "status": "released", "...": "..." },
    "events": ["event-0001"]
  },
  "events": ["event-0001"]
}
```

Error (machine codes: `USAGE_ERROR`, `NOT_FOUND`, `CONFIG_ERROR`,
`VALIDATION_ERROR`, `CONFLICT`):

```json
{
  "ok": false,
  "command": "release.tag",
  "error": {
    "code": "USAGE_ERROR",
    "message": "Release version already exists: 1.2.0",
    "exit_code": 2,
    "remediation": ["Run `releaseledger release show 1.2.0`."]
  }
}
```

## Python API

A narrow, stable surface is re-exported from `releaseledger.api`:

```python
from releaseledger.api.releases import create_release, update_release, show_release
from releaseledger.api.entries import (
    add_release_entry,
    add_many_release_entries,
    update_release_entry,
    lint_release_entries,
    build_entry_prompt,
)
from releaseledger.api.changelog import build_changelog_file, render_changelog_section
from releaseledger.api.config import (
    load_project_locator,
    render_default_releaseledger_toml,
    storage_where,
    config_show,
    config_set_releaseledger_dir,
)
```

Services return plain dict payloads and raise `releaseledger.errors.LaunchError`
on failure; they never print or call `typer.Exit`.

## External state configuration

By default, releaseledger stores state in a `.releaseledger/` directory inside
the workspace. Projects that use a consolidated sibling state repository can
configure an external directory with a portable relative path:

```toml
# .releaseledger.toml
releaseledger_dir = "../ledger/release/releaseledger"
releaseledger_dir_policy = "external"
```

To set this via the CLI:

```bash
releaseledger init --releaseledger-dir ../ledger/release/releaseledger --external-dir
# or for an existing project:
releaseledger config set releaseledger_dir ../ledger/release/releaseledger --external-dir
```

Relative paths that escape the workspace root are rejected unless
`releaseledger_dir_policy` is set to `"external"` or `--external-dir` is passed.
Absolute paths are accepted for backward compatibility but are not portable.

## Storage diagnostics

Use `storage where` to inspect the effective storage location, layout health,
and config source without mutating state:

```bash
releaseledger storage where
releaseledger --json storage where
```

Human output example:

```text
Workspace: /home/user/project
Config: /home/user/project/.releaseledger.toml
Storage: /home/user/project/.releaseledger
Ledger: main
Inside workspace: yes
Source: dotfile
Layout: ok
Indexes: ok
```

Use `config show` to inspect the validated configuration and resolved paths:

```bash
releaseledger config show
releaseledger --json config show
```

## Development

```bash
python -m pip install -e ".[dev]"
pytest -q
ruff check .
mypy releaseledger
python -m build
```

The project ships `py.typed` and targets Python 3.10+.

## License

Apache-2.0
