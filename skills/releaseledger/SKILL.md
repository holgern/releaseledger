---
name: releaseledger
description: Manage project-local release records, release entries, changelog source, and CHANGELOG.md builds
license: Apache-2.0
compatibility: opencode
metadata:
  audience: coding-agents
  workflow: release-management
---

## When to use this skill

Use releaseledger when a project needs durable, project-local release state: release records, release notes, changelog entries, generated changelog source, or updates to `CHANGELOG.md`.

Releaseledger is separate from taskledger. Do not treat `.releaseledger/` as task state and do not require taskledger to be installed.

## Never do these things

- Do not edit `.releaseledger/` storage files directly. Use releaseledger commands or the public `releaseledger.api.*` surface.
- Do not invent a release date. Use the date explicitly provided by the user, the persisted `released_at` value, or an unreleased heading.
- Do not include internal entries unless the user explicitly asks for internal release notes or passes an include-internal option.
- Do not silently overwrite an existing release section in `CHANGELOG.md`. Use the supported replace/update option only when explicitly requested.
- Do not duplicate an existing release heading.
- Do not remove existing historical changelog sections.
- Do not change release status just to build a changelog.
- Do not import or call `releaseledger.storage.*`, `releaseledger.services.*`, or `releaseledger.domain.*` from ad-hoc scripts during normal release work. Use the CLI or public `releaseledger.api.*`.
- Do not create or switch to external releaseledger state unless the project config already declares it or the user explicitly requests it.
- Prefer portable relative paths with `releaseledger_dir_policy = "external"` over machine-specific absolute paths.
- If releaseledger reports that releaseledger_dir escapes the workspace root, run `releaseledger storage where` or `releaseledger config show` before mutating anything.
- Do not treat generated changelog source as final prose unless the command requested a final build.
- Do not import taskledger, inspect `.taskledger/`, or dereference task refs.
  Accept taskledger evidence only as caller-supplied context and global refs.

## Core agent command path

Use this path first for routine release work:

```text
releaseledger --version
releaseledger init
releaseledger release list
releaseledger release show VERSION
releaseledger release create VERSION
releaseledger release update VERSION
releaseledger release tag VERSION
releaseledger release finalize VERSION
releaseledger entry add VERSION --kind KIND --summary TEXT
releaseledger entry add-many VERSION --file FILE --dry-run
releaseledger entry show VERSION ENTRY_ID
releaseledger entry update VERSION ENTRY_ID
releaseledger entry import VERSION --file FILE
releaseledger entry list VERSION
releaseledger entry lint VERSION --strict
releaseledger entry prompt VERSION --source-ref REF --context-file FILE
releaseledger changelog VERSION --format markdown|json
releaseledger build VERSION --dry-run
releaseledger build VERSION --target-file CHANGELOG.md
releaseledger storage where
releaseledger config show
releaseledger config set releaseledger_dir PATH [--external-dir]
```

Root options belong before the subcommand:

```text
releaseledger --cwd PATH --json release show VERSION
```

## Fresh context entry protocol

1. Run `releaseledger --version`.
2. Run `releaseledger storage where` or `releaseledger --json storage where`.
3. Run `releaseledger config show` to verify the resolved configuration.
4. Run `releaseledger release list`.
5. For a known release, run `releaseledger release show VERSION`.
6. Run `releaseledger entry list VERSION`.
7. Generate machine context when needed:
   `releaseledger changelog VERSION --format json`.
8. Do not inspect `.releaseledger/` internals unless the CLI cannot start and the user explicitly requested forensic inspection.

## Release creation protocol

1. Create a planned or candidate release:
   `releaseledger release create VERSION --title "Release VERSION"`.
2. Set `--previous VERSION` when the previous version is known and should appear in generated context.
3. Set `--released-at YYYY-MM-DD` only when the date is known.
4. Use `releaseledger release tag VERSION` for an immediately released/tagged release.
5. Use `releaseledger release finalize VERSION --released-at YYYY-MM-DD` to transition an existing planned/draft/candidate release to released.
6. Verify with:
   `releaseledger release show VERSION`.

## Changelog entry protocol

Use this when the user asks to add release-note material.

1. Resolve the target version:
   `releaseledger release show VERSION`.
2. Add entries with one of the controlled kinds:
   `added`, `changed`, `fixed`, `removed`, `deprecated`, `security`, `docs`, `quality`, `internal`.
   `documentation` and `doc` normalize to `docs`.
3. Keep summaries one line, user-facing, and free of trailing periods unless the project style requires punctuation.
4. Use `--body` for longer explanation and `--path`, `--issue`, and `--pr` for traceability.
5. Use `--breaking` for breaking changes.
6. Use `--internal` only for implementation-only notes that should be hidden from public changelogs by default.
7. Verify with:
   `releaseledger entry list VERSION`.
8. Use `--status accepted` for final notes, `draft` for incomplete notes, and
   `rejected` for retained-but-excluded proposals.
9. Link external evidence with `--source-ref tl:task-0103`; never make
   releaseledger inspect the external ledger.

Example:

```bash
releaseledger entry add 1.2.0 --kind added \
  --summary "Added release bundle storage" \
  --status accepted \
  --source-ref tl:task-0103 \
  --path releaseledger/storage/store.py
```

## Batch entry protocol

When release notes need taskledger context, first use taskledger to inspect
tasks and validation evidence. Then pass that evidence into releaseledger as
opaque context and global refs:

```bash
releaseledger entry prompt VERSION --source-ref tl:task-0103 \
  --context-file /tmp/task-0103.json --output /tmp/prompt.md
releaseledger entry add-many VERSION --file /tmp/VERSION-entries.yaml --dry-run
releaseledger entry add-many VERSION --file /tmp/VERSION-entries.yaml
releaseledger entry lint VERSION --strict
releaseledger entry list VERSION
```

Batch creation validates every entry before writing any entry. If any item is
invalid, correct the YAML and rerun the dry run; do not add entries one at a
time to bypass atomic validation.

## Changelog source protocol

Use this when the user wants release-note source material for review or drafting.

```bash
releaseledger changelog VERSION --target-changelog CHANGELOG.md --release-date YYYY-MM-DD
releaseledger changelog VERSION --format json
releaseledger changelog VERSION --include-internal
releaseledger changelog VERSION --include-status accepted --include-status draft
releaseledger changelog VERSION --lint
```

Rules:

1. Treat `releaseledger changelog VERSION` as source/context unless the command name or option explicitly says build/update.
2. Check whether internal entries were filtered.
3. Preserve warnings, release metadata, and entry grouping when handing source to a human or another tool.
4. If no date is provided and the release has no persisted `released_at`, keep the output unreleased or explicitly say no date was available.

## CHANGELOG.md build protocol

Use this when the user asks to build, generate, or update `CHANGELOG.md`.

1. Generate a strict dry run first:
   `releaseledger build VERSION --dry-run --strict --target-file CHANGELOG.md`.
2. Inspect the rendered section:
   - heading version is correct
   - release date is exact, omitted, or marked unreleased according to user intent
   - internal entries are absent unless requested
   - groups appear in deterministic order
   - breaking changes are visible
3. Apply the build:
   `releaseledger build VERSION --target-file CHANGELOG.md`.
4. Read `CHANGELOG.md` back and verify:
   - no duplicate release heading exists
   - new section is below `## Unreleased` when that heading exists
   - prior release history is preserved
   - the file has one final newline
5. If the target already has the version section, do not replace it unless the user explicitly requested replacement. Use the supported replace flag and state that replacement was used.
6. Accepted entries are included by default. Include draft entries only for
   explicitly draft output and preserve the draft-quality warning.
7. Do not use `--allow-empty` unless an empty release section is intentional.

## Templating protocol

Releaseledger changelog templates are configured in `.releaseledger.toml` under `[changelog]`.

Expected keys:

```toml
[changelog]
output = "CHANGELOG.md"
trim = true
render_always = false
header = ""
body = """
## {% if release.date %}[{{ release.version }}] - {{ release.date }}{% else %}[{{ release.version }}] - Unreleased{% endif %}

{% for group in groups %}
### {{ group.title }}
{% for entry in group.entries %}
- {% if entry.breaking %}**BREAKING:** {% endif %}{{ entry.summary }}
{% endfor %}

{% endfor %}
"""
footer = "<!-- generated by releaseledger -->"
postprocessors = []
```

Template context should include at least:

```text
project.name
release.version
release.title
release.status
release.date
release.previous_version
release.changelog_file
entries
groups
releases
```

Use templates only for rendering. Do not let templates mutate releaseledger state or read files.

## JSON mode protocol

When machine output is needed, `--json` is root-level:

```bash
releaseledger --json release show 1.2.0
releaseledger --json build 1.2.0 --dry-run
```

Do not append `--json` after the subcommand unless releaseledger explicitly adds that local option later.

## CLI failure protocol

If a `releaseledger ...` command fails with a Python traceback:

1. Stop mutating release state.
2. Run exactly one read-only probe:
   `releaseledger --version`.
3. If startup still fails, report that the releaseledger CLI is broken and no mutation was recorded.
4. If startup succeeds, rerun the failed command once with the same arguments.
5. For repeated failure, inspect command help and use explicit options rather than guessing.

If `releaseledger_dir escapes the workspace root`, do not edit `.releaseledger.toml` manually.
Use `releaseledger config set releaseledger_dir PATH --external-dir` when the sibling state directory is intentional.
Or use `releaseledger config set releaseledger_dir .releaseledger` to reset to workspace-local.

## Public API protocol

Prefer CLI for agent work. If Python integration is required, import only public modules:

```python
from releaseledger.api.releases import create_release, update_release, show_release
from releaseledger.api.entries import (
    add_release_entry,
    add_many_release_entries,
    update_release_entry,
    lint_release_entries,
    build_entry_prompt,
)
from releaseledger.api.config import load_project_locator, render_default_releaseledger_toml
```

Do not couple external code to internal storage paths or private service functions unless the user explicitly requests package development work.
