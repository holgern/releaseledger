Commands
========

Root options
------------

.. code-block:: text

   releaseledger --cwd PATH ...
   releaseledger --json ...
   releaseledger --version

``--cwd`` runs as if started from another directory. ``--json`` emits
deterministic JSON envelopes.

Project commands
----------------

.. code-block:: text

   releaseledger init [--releaseledger-dir PATH] [--project-name NAME]
                     [--external-dir] [--force]
   releaseledger storage where
   releaseledger config show
   releaseledger config set releaseledger_dir PATH [--external-dir]

Release commands
----------------

.. code-block:: text

   releaseledger release create VERSION [--title TEXT] [--status STATUS]
                                        [--previous VERSION] [--note TEXT]
                                        [--changelog-file PATH]
                                        [--released-at YYYY-MM-DD]
                                        [--boundary-ref REF]
                                        [--source-ref REF]...
                                        [--source-count N]
   releaseledger release update VERSION [release metadata options]
   releaseledger release tag VERSION [release metadata options]
   releaseledger release finalize VERSION [--released-at YYYY-MM-DD]
                                          [--changelog-file PATH]
   releaseledger release list
   releaseledger release show VERSION

``release tag`` creates a release with status ``released``. ``release finalize``
transitions an existing release to ``released``.

Entry commands
--------------

.. code-block:: text

   releaseledger entry add VERSION --kind KIND --summary TEXT [--body TEXT]
                                  [--status STATUS] [--audience TEXT]
                                  [--scope SCOPE]... [--source-ref REF]...
                                  [--path PATH]... [--issue REF]... [--pr REF]...
                                  [--breaking] [--internal] [--dry-run]
   releaseledger entry add-many VERSION --file FILE [--dry-run]
   releaseledger entry update VERSION ENTRY_ID [entry metadata options]
   releaseledger entry show VERSION ENTRY_ID
   releaseledger entry import VERSION --file FILE [--replace]
                                      [--source-ledger LEDGER]
   releaseledger entry list VERSION
   releaseledger entry lint VERSION [--strict] [--include-status STATUS]...
   releaseledger entry prompt VERSION [--source-ref REF]...
                                      [--context-file FILE]
                                      [--format markdown|json]
                                      [--output PATH]

Batch file format
-----------------

``entry add-many`` expects YAML with a top-level ``entries`` list:

.. code-block:: yaml

   entries:
     - kind: added
       summary: Added release bundle storage
       body: >-
         The storage layer now writes release records, entries, events, and indexes.
       status: accepted
       audience: developer
       scopes: [storage]
       source_refs: [tl:task-0103]
       paths:
         - releaseledger/storage/store.py
       issues: []
       prs: []
       breaking: false
       internal: false

Changelog commands
------------------

.. code-block:: text

   releaseledger changelog VERSION [--format markdown|json] [--output PATH]
                                   [--include-internal]
                                   [--target-changelog PATH]
                                   [--release-date YYYY-MM-DD]
                                   [--include-sources]
                                   [--include-status STATUS]... [--lint]

   releaseledger build VERSION [--target-file PATH]
                               [--release-date YYYY-MM-DD]
                               [--unreleased]
                               [--include-internal]
                               [--template NAME]
                               [--dry-run]
                               [--replace-existing]
                               [--format markdown|json]
                               [--include-status STATUS]...
                               [--strict]
                               [--allow-empty]
