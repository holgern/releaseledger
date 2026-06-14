Storage and configuration
=========================

Default layout
--------------

A normal project stores release state inside the workspace:

.. code-block:: toml

   config_version = 1
   releaseledger_dir = ".releaseledger"

   ledger_ref = "main"
   ledger_parent_ref = ""
   ledger_next_entry_number = 1
   ledger_branch_guard = "off"

   [ledger]
   code = "rl"
   name = "releaseledger"

   [release]
   default_changelog = "CHANGELOG.md"
   default_status = "planned"
   allow_dirty_worktree = true

Storage tree:

.. code-block:: text

   .releaseledger/
     ledgers/
       main/
         releases/
           <version>/
             release.md
             entries/
               entry-0001.md
         events/
           events.jsonl
         indexes/
           releases.json
           entries.json

External state directories
--------------------------

Projects that keep generated state in a sibling repository can opt in to an
external path:

.. code-block:: toml

   releaseledger_dir = "../ledger/release/releaseledger"
   releaseledger_dir_policy = "external"

The CLI form is:

.. code-block:: bash

   releaseledger init \
     --releaseledger-dir ../ledger/release/releaseledger \
     --external-dir

   releaseledger config set releaseledger_dir \
     ../ledger/release/releaseledger \
     --external-dir

Relative paths that escape the workspace are rejected unless the external
policy is explicit.

Diagnostics
-----------

Inspect effective paths and layout health without mutating state:

.. code-block:: bash

   releaseledger storage where
   releaseledger --json storage where
   releaseledger config show
   releaseledger --json config show
