Development
===========

Setup
-----

.. code-block:: bash

   python -m pip install -e ".[dev]"

Validation
----------

.. code-block:: bash

   pytest -q
   ruff check .
   mypy releaseledger
   python -m build

Documentation
-------------

.. code-block:: bash

   python -m pip install -e ".[docs]"
   sphinx-build -b html docs docs/_build/html

Packaging
---------

The package uses setuptools and setuptools-scm. ``releaseledger/_version.py`` is
generated version metadata and is included in the context pack for inspection.

Typing
------

The project ships ``py.typed`` and targets Python 3.10 or newer.
