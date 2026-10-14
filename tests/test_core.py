import pytest

from prismcv import CV, PrismError, Source, max_pages, target_languages

DESIGN = {"languages": {"en": "english", "zh": "mandarin_chinese"}}
TITLES = {"work": {"en": "Work", "zh": "工作"}, "skills": {"en": "Skills", "zh": "技能"},
          "profile": {"en": "Profile", "zh": "简介"}}
ENTRIES = {
    "acme": {
        "company": {"en": "Acme", "zh": "顶点"},
        "position": "Engineer",
        "start_date": "2024-01",
        "highlights": [
            {"en": "Only in English", "zh": None},
            {"en": "Both", "zh": "两种"},
        ],
    },
    "acme@short": {"highlights": [{"en": "Short", "zh": "短"}]},
    "acme-alias": {"base": "acme", "position": "Lead"},
    "skills": [{"label": "Languages", "details": "Python"}, {"label": "Tools", "details": "Git"}],
    "about": {"text": {"en": "Hello", "zh": "你好"}},
}


def make(entries=None, header=None, titles=None, design=None):
    cv = {"header": header if header is not None else {"name": {"en": "Ann", "zh": "安"}},
          "sections": titles if titles is not None else TITLES}
    return CV(cv, design or DESIGN, entries if entries is not None else ENTRIES)


def section(cv, target, lang, title):
    return cv.assemble(target, lang).doc["cv"]["sections"][title]


def raises(fn, message):
    with pytest.raises(PrismError) as e:
        fn()
    assert message in str(e.value)
    return e.value.issues[0]


# Localized values

def test_localizes_and_omits_null():
    work = section(make(), {"sections": {"work": ["acme"]}}, "zh", "工作")
    assert work[0]["company"] == "顶点"
    assert work[0]["highlights"] == ["两种"]


def test_missing_language_points_at_the_entry():
    entries = dict(ENTRIES, acme=dict(ENTRIES["acme"], company={"en": "Acme"}))
    issue = raises(lambda: make(entries).assemble({"sections": {"work": ["acme"]}}, "zh"), "missing 'zh'")
    assert issue.source == Source("entry", "acme", ("company",))


def test_keys_next_to_language_keys_are_reported():
    entries = dict(ENTRIES, acme=dict(ENTRIES["acme"], location={"en": "London", "UK": None}))
    raises(lambda: make(entries).assemble({"sections": {"work": ["acme"]}}, "en"), "unexpected keys ['UK']")


# Entries and items

def test_variant_by_name_and_by_base():
    cv = make()
    work = section(cv, {"sections": {"work": ["acme@short", "acme-alias"]}}, "en", "Work")
    assert work[0]["highlights"] == ["Short"] and work[0]["company"] == "Acme"
    assert work[1]["position"] == "Lead" and work[1]["highlights"] == ["Only in English", "Both"]


def test_override_and_inline_and_group_and_paragraph():
    cv = make()
    target = {"sections": {
        "work": [{"acme": {"position": "Intern"}}, {"company": "Solo", "position": "Owner"}],
        "skills": ["skills"],
        "profile": ["about"],
    }}
    doc = cv.assemble(target, "en").doc["cv"]["sections"]
    assert [e["position"] for e in doc["Work"]] == ["Intern", "Owner"]
    assert [e["label"] for e in doc["Skills"]] == ["Languages", "Tools"]
    assert doc["Profile"] == ["Hello"]


def test_unknown_id_points_at_the_target_item():
    issue = raises(lambda: make().assemble({"sections": {"work": ["acme", "nope"]}}, "en"), "unknown id 'nope'")
    assert issue.source == Source("target", "work", (1,))


def test_circular_base():
    entries = {"a": {"base": "b", "name": "A"}, "b": {"base": "a", "name": "B"}}
    raises(lambda: make(entries, titles={"x": "X"}).assemble({"sections": {"x": ["a"]}}, "en"), "circular base")


def test_mixed_entry_types():
    issue = raises(lambda: make().assemble({"sections": {"work": ["acme", "skills"]}}, "en"), "mixed entry types")
    assert issue.source == Source("target", "work")


def test_titles_from_cv_and_target():
    cv = make()
    doc = cv.assemble({"sections": {"work": {"title": "Experience", "entries": ["acme"]}}}, "en").doc
    assert list(doc["cv"]["sections"]) == ["Experience"]
    raises(lambda: cv.assemble({"sections": {"other": ["acme"]}}, "en"), "no title")


def test_header_override_and_file_stem():
    cv = make()
    doc = cv.assemble({"header": {"email": "a@b.com"}, "sections": {}}, "zh").doc
    assert doc["cv"]["name"] == "安" and doc["cv"]["email"] == "a@b.com"
    assert cv.file_stem("zh") == "Ann_CV_zh"


def test_design_per_language_and_locale():
    design = dict(DESIGN, design={"theme": "classic"}, zh={"typography": {"font_family": "Noto Sans SC"}})
    cv = make(design=design)
    zh = cv.assemble({"sections": {}}, "zh").doc
    en = cv.assemble({"sections": {}}, "en").doc
    assert zh["design"]["typography"]["font_family"] == "Noto Sans SC"
    assert "typography" not in en["design"]
    assert zh["locale"]["language"] == "mandarin_chinese"
    # RenderCV needs a theme; classic is its default.
    assert make().assemble({"sections": {}}, "en").doc["design"] == {"theme": "classic"}


def test_target_checks():
    cv = make()
    assert target_languages({}, cv) == ["en", "zh"]
    raises(lambda: target_languages({"langs": ["fr"]}, cv), "'fr' is not listed")
    assert max_pages({"max_pages": 2}) == 2
    raises(lambda: max_pages({"max_pages": 0}), "positive whole number")


def test_does_not_change_its_input():
    import copy
    before = copy.deepcopy(ENTRIES)
    make().assemble({"sections": {"work": [{"acme": {"position": "X"}}, "acme@short"]}}, "en")
    assert ENTRIES == before
