"""Single source of truth for the package version.

Kept in its own module so that submodules can read the version without
importing the package root, which would create a circular import during
initialization.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.5.5"
