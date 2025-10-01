"""ADS-B ATC Textual TUI package.

This package modularizes the original monolithic script into maintainable modules
without changing the runtime behavior or CLI surface.
"""

from .cli import main  # re-export for convenience

__all__ = ["main"]

__version__ = "0.1.0"
