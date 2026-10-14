"""PrismCV: one source, every CV."""

from .core import CV, Assembled, Issue, PrismError, Source, literal, max_pages, target_languages
from .validate import validate

__version__ = "0.1.2"

__all__ = ["CV", "Assembled", "Issue", "PrismError", "Source", "literal", "max_pages",
           "target_languages", "validate"]
