"""Check RenderCV input with RenderCV's own models, reporting problems against their sources."""

from __future__ import annotations

import copy

from rendercv.exception import RenderCVUserError, RenderCVUserValidationError
from rendercv.schema import rendercv_model_builder
from rendercv.schema.models.rendercv_model import RenderCVModel

from .core import Assembled, Issue, PrismError


def validate(assembled: Assembled) -> list[Issue]:
    """Problems RenderCV would report for this input, each with the source it came from."""
    try:
        _build_model(assembled)
    except PrismError as e:
        return e.issues
    return []


def _build_model(assembled: Assembled) -> RenderCVModel:
    """Build a fresh, isolated model or raise PrismError with the existing diagnostics."""
    try:
        return rendercv_model_builder.build_rendercv_model_from_commented_map(
            copy.deepcopy(assembled.doc)
        )
    except Exception as e:
        raise PrismError(_issues_from_error(assembled, e)) from e


def _issues_from_error(
    assembled: Assembled,
    error: Exception,
    action: str = "check this CV",
) -> list[Issue]:
    """Keep model and template errors on the same source-aware diagnostic path."""
    if isinstance(error, RenderCVUserValidationError):
        errors = [
            (tuple(v.schema_location or ()), v.message) for v in error.validation_errors
        ]
    elif isinstance(error, RenderCVUserError):
        return [Issue(error.message or "RenderCV rejected the input")]
    else:
        return [Issue(f"RenderCV could not {action}: {type(error).__name__}: {error}")]

    issues = []
    for loc, message in errors:
        # A section reports "there are problems with the entries" above the
        # precise problems; keep only the precise ones.
        if any(other != loc and other[: len(loc)] == loc for other, _ in errors):
            continue
        issues.append(Issue(message, assembled.source_of(loc), loc))
    return issues
