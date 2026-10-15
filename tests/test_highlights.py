"""Stable bullet selection, metadata validation, and sources before localization."""

import copy

import pytest

from prismcv import PrismError, Source, validate
from test_core import make


BULLETS = [
    "Legacy shared",
    {"en": "Legacy English", "zh": "旧中文"},
    {"id": "drivers", "en": "Drivers", "zh": "驱动"},
    {"id": "shared", "text": "Shared text"},
    {"id": "localized", "text": {"en": "Localized", "zh": "本地化"}},
    {"text": "Optional id"},
]


def cv_with(bullets=BULLETS, **entries):
    return make({"job": {"company": "Acme", "position": "Engineer", "highlights": bullets}, **entries})


def assemble(cv=None, item="job", lang="en", **kwargs):
    return (cv or cv_with()).assemble({"sections": {"work": [item]}}, lang, **kwargs)


def highlights(result, title="Work"):
    return result.doc["cv"]["sections"][title][0]["highlights"]


def test_all_bullet_forms_and_no_metadata():
    result = assemble()
    assert highlights(result) == ["Legacy shared", "Legacy English", "Drivers", "Shared text", "Localized", "Optional id"]
    assert validate(result) == []
    assert highlights(assemble(lang="zh"), "工作") == ["Legacy shared", "旧中文", "驱动", "Shared text", "本地化", "Optional id"]


@pytest.mark.parametrize("hidden, expected", [
    (["drivers"], ["Legacy shared", "Legacy English", "Shared text", "Localized", "Optional id"]),
    (["drivers", "shared"], ["Legacy shared", "Legacy English", "Localized", "Optional id"]),
    ([], ["Legacy shared", "Legacy English", "Drivers", "Shared text", "Localized", "Optional id"]),
])
def test_hide_with_field_override(hidden, expected):
    result = assemble(item={"job": {"hide": hidden, "position": "Lead"}})
    assert highlights(result) == expected
    entry = result.doc["cv"]["sections"]["Work"][0]
    assert entry["position"] == "Lead"
    assert "hide" not in entry
    assert validate(result) == []


def test_hide_follows_reordering_and_new_bullets_default_to_visible():
    bullets = list(reversed(BULLETS)) + ["New bullet"]
    assert highlights(assemble(cv_with(bullets), {"job": {"hide": ["drivers", "shared"]}})) == [
        "Optional id", "Localized", "Legacy English", "Legacy shared", "New bullet"]


def test_inheritance_and_override_resolved_before_hide():
    cv = cv_with(**{"job@lead": {"position": "Lead"},
                    "job@short": {"highlights": [{"id": "short", "text": "Short"}]}})
    assert "Drivers" not in highlights(assemble(cv, {"job@lead": {"hide": ["drivers"]}}))
    result = assemble(cv, {"job@short": {"highlights": BULLETS, "hide": ["drivers"]}})
    assert "Drivers" not in highlights(result)
    for item in ({"job@short": {"hide": ["drivers"]}}, {"job": {"highlights": [], "hide": ["drivers"]}}):
        with pytest.raises(PrismError, match="unknown hidden bullet id 'drivers'") as exc:
            assemble(cv, item)
        eid = next(iter(item))
        assert exc.value.issues[0].source == Source("target", "work", (0, eid, "hide"))


def test_filter_before_localization_and_keep_original_sources():
    bullets = [{"id": "hide", "en": "Missing Chinese"},
               {"id": "omit", "en": "English only", "zh": None},
               {"id": "stay", "text": {"en": "Stay", "zh": "保留"}},
               {"en": "No id", "zh": "无编号"}]
    result = assemble(cv_with(bullets), {"job": {"hide": ["hide"]}}, "zh")
    assert highlights(result, "工作") == ["保留", "无编号"]
    at = ("cv", "sections", "工作", 0, "highlights")
    assert result.source_of(at + (0,)) == Source("entry", "job", ("highlights", "stay", "text", "zh"))
    assert result.source_of(at + (1,)) == Source("entry", "job", ("highlights", 3, "zh"))


def test_sources_for_variant_override_and_missing_translation():
    cv = cv_with(**{"job@short": {"highlights": [{"id": "short", "en": "Short"}]}})
    result = assemble(cv, "job@short")
    at = ("cv", "sections", "Work", 0, "highlights", 0)
    assert result.source_of(at) == Source("entry", "job@short", ("highlights", "short", "en"))
    result = assemble(item={"job": {"highlights": [{"id": "new", "text": "New"}]}})
    assert result.source_of(at) == Source("target", "work", (0, "job", "highlights", "new", "text"))
    with pytest.raises(PrismError, match="missing 'zh'") as exc:
        assemble(cv, "job@short", "zh")
    assert exc.value.issues[0].source == Source("entry", "job@short", ("highlights", "short"))


@pytest.mark.parametrize("bullets", [
    [{"id": "dup", "text": "A"}, {"id": "dup", "en": "B"}],
    [{"id": "dup", "text": "A"}, {"id": "dup", "text": "B"}],
])
def test_duplicate_ids_are_errors_even_when_hidden(bullets):
    with pytest.raises(PrismError, match="duplicate bullet id 'dup' in entry 'job'") as exc:
        assemble(cv_with(bullets), {"job": {"hide": ["dup"]}})
    assert exc.value.issues[0].source == Source("entry", "job", ("highlights", "dup"))


@pytest.mark.parametrize("hide", [None, "drivers", {"drivers": True}, [1], [""], False])
def test_malformed_hide_is_structured_error(hide):
    with pytest.raises(PrismError, match="hide.*must be a list") as exc:
        assemble(item={"job": {"hide": hide}})
    assert exc.value.issues[0].source == Source("target", "work", (0, "job", "hide"))


def test_misplaced_hide_is_an_error_instead_of_rendercv_metadata():
    with pytest.raises(PrismError, match="hide belongs") as exc:
        assemble(item={"company": "Acme", "position": "Dev", "hide": ["x"]})
    assert exc.value.issues[0].source == Source("target", "work", (0, "hide"))


def test_hide_all_and_missing_highlights():
    assert highlights(assemble(cv_with([{"id": "x", "text": "X"}]), {"job": {"hide": ["x"]}})) == []
    cv = make({"job": {"company": "Acme", "position": "Dev"}})
    with pytest.raises(PrismError, match="unknown hidden bullet id 'x'"):
        assemble(cv, {"job": {"hide": ["x"]}})


@pytest.mark.parametrize("bullet", [
    {"id": "only"}, {"id": 2, "text": "Bad"}, {"id": "", "text": "Bad"},
    {"id": None, "text": "Bad"}, {"id": "x", "text": 2},
    {"text": "Bad", "en": "Mixed"}, {"id": "x", "en": "Bad", "other": "No"},
    {}, None, 2, ["No"], {"en": ["No"]}, {"text": None},
])
def test_malformed_bullet_is_structured_error(bullet):
    with pytest.raises(PrismError, match="bullet") as exc:
        assemble(cv_with([bullet]))
    assert exc.value.issues[0].source.kind == "entry"
    assert exc.value.issues[0].source.key == "job"


def test_inline_and_group_bullet_sources():
    job = {"company": "Acme", "position": "Dev", "highlights": [{"id": "x", "text": "X"}]}
    result = assemble(item=job)
    at = ("cv", "sections", "Work", 0, "highlights", 0)
    assert result.source_of(at) == Source("target", "work", (0, "highlights", "x", "text"))
    result = assemble(make({"jobs": [job]}), "jobs")
    assert result.source_of(at) == Source("entry", "jobs", (0, "highlights", "x", "text"))


def test_inputs_unchanged_and_literal_mode_preserved():
    cv = cv_with([{"id": "x", "text": "#emph[hello] - world"}])
    before = copy.deepcopy(cv.entries)
    target = {"sections": {"work": [{"job": {"hide": [], "position": "Lead"}}]}}
    target_before = copy.deepcopy(target)
    assert highlights(cv.assemble(target, "en")) == ["#emph[hello] - world"]
    assert highlights(cv.assemble(target, "en", literal=True)) == ["#⁠emph[hello] - world"]
    assert cv.entries == before
    assert target == target_before
