"""Sphinx configuration for releaseledger."""

from __future__ import annotations

import os
import sys
from importlib import metadata

sys.path.insert(0, os.path.abspath(".."))

project = "releaseledger"
copyright = "2026, Releaseledger Contributors"
author = "Releaseledger Contributors"

try:
    release = metadata.version("releaseledger")
except metadata.PackageNotFoundError:
    try:
        from releaseledger._version import __version__ as release
    except ImportError:
        release = "0.1.0"

version = ".".join(release.split(".")[:2])

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx.ext.todo",
    "sphinx.ext.coverage",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "sphinx_rtd_theme"
html_static_path: list[str] = []
html_title = f"{project} {version}"

autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "special-members": "__init__",
    "undoc-members": True,
    "exclude-members": "__weakref__",
}

napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = False
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = False
napoleon_use_admonition_for_notes = False
napoleon_use_admonition_for_references = False
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True

intersphinx_mapping = {
    "python": ("https://docs.python.org/3/", None),
}

todo_include_todos = True
