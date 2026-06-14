Concepts
========

Release
-------

A release is a versioned record stored as ``release.md`` with YAML front matter
and an optional Markdown body. It tracks status, previous version, release date,
source boundary, source refs, and changelog file metadata.

Release statuses are:

- ``planned``
- ``draft``
- ``candidate``
- ``released``
- ``yanked``

Entry
-----

An entry is one release-note item stored under
``releases/<version>/entries/entry-NNNN.md``. Entries are grouped by kind for
changelog rendering.

Entry kinds are:

- ``added``
- ``changed``
- ``fixed``
- ``removed``
- ``deprecated``
- ``security``
- ``docs``
- ``quality``
- ``internal``

``documentation`` and ``doc`` are accepted aliases for ``docs``.

Entry statuses are ``draft``, ``accepted``, and ``rejected``. Changelog builds
include accepted entries by default.

Event
-----

Every mutation appends a JSON object to ``events/events.jsonl``. Events provide
a simple audit trail and deterministic event IDs.

Index
-----

Releaseledger rebuilds ``indexes/releases.json`` and ``indexes/entries.json``
after mutations. Indexes are derived state and should remain deterministic.

Global refs
-----------

External provenance is recorded as caller-supplied global refs, for example
``tl:task-0103``. Releaseledger stores these refs but does not resolve or
validate external ledger state.
