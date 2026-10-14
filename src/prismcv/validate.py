"""Check RenderCV input with RenderCV's own models, reporting problems against their sources."""

from __future__ import annotations

import copy

from .core import Assembled, Issue


def validate(assembled: Assembled) -> list[Issue]:
    """Problems RenderCV would report for this input, each with the source it came from."""
    from rendercv.exception import RenderCVUserError, RenderCVUserValidationError
    from rendercv.schema.rendercv_model_builder import build_rendercv_model_from_commented_map

    try:
        build_rendercv_model_from_commented_map(copy.deepcopy(assembled.doc))
    except RenderCVUserValidationError as e:
        errors = [(tuple(v.schema_location or ()), v.message) for v in e.validation_errors]
    except RenderCVUserError as e:
        return [Issue(e.message or "RenderCV rejected the input")]
    except Exception as e:  # a failure inside RenderCV's own checks
        return [Issue(f"RenderCV could not check this CV: {type(e).__name__}: {e}")]
    else:
        return []

    issues = []
    for loc, message in errors:
        # A section reports "there are problems with the entries" above the
        # precise problems; keep only the precise ones.
        if any(other != loc and other[:len(loc)] == loc for other, _ in errors):
            continue
        issues.append(Issue(message, assembled.source_of(loc), loc))
    return issues
