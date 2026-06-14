Quickstart
==========

Install
-------

.. code-block:: bash

   python -m pip install releaseledger

For development:

.. code-block:: bash

   python -m pip install -e ".[dev]"

Initialize a project
--------------------

.. code-block:: bash

   releaseledger init

This creates ``.releaseledger.toml`` and the default state layout:

.. code-block:: text

   .releaseledger/
     ledgers/
       main/
         releases/
         events/
         indexes/

Create a release
----------------

.. code-block:: bash

   releaseledger release create 1.2.0 \
     --title "Release 1.2.0" \
     --boundary-ref tl:task-0105 \
     --source-ref tl:task-0103

Add entries
-----------

.. code-block:: bash

   releaseledger entry add 1.2.0 \
     --kind added \
     --summary "Added release bundle storage" \
     --status accepted \
     --source-ref tl:task-0103

Validate entries:

.. code-block:: bash

   releaseledger entry lint 1.2.0 --strict

Render changelog output
-----------------------

Use ``changelog`` to produce review context:

.. code-block:: bash

   releaseledger changelog 1.2.0 \
     --target-changelog CHANGELOG.md \
     --release-date 2026-06-13

Use ``build`` to render and insert a final section:

.. code-block:: bash

   releaseledger build 1.2.0 \
     --dry-run \
     --strict \
     --target-file CHANGELOG.md

   releaseledger build 1.2.0 \
     --release-date 2026-06-13 \
     --strict \
     --target-file CHANGELOG.md
