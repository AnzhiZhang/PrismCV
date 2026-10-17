"""PrismCV: one source, every CV."""

from .core import (
    CV,
    Assembled,
    Issue,
    PrismError,
    Source,
    literal,
    max_pages,
    target_languages,
)
from .portability import FilesError, read_files, write_files
from .validate import validate

__version__ = "0.1.3"

__all__ = [
    "CV",
    "Assembled",
    "FilesError",
    "Issue",
    "PrismError",
    "Source",
    "literal",
    "max_pages",
    "read_files",
    "target_languages",
    "validate",
    "write_files",
]
