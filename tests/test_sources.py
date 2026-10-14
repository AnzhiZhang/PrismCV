from prismcv import Source

from test_core import make


def test_bullet_index_follows_omitted_bullets():
    # In Chinese the first bullet is left out, so the output's first bullet is the entry's second.
    a = make().assemble({"sections": {"work": ["acme"]}}, "zh")
    assert a.source_of(("cv", "sections", "工作", 0, "highlights", 0)) == Source("entry", "acme", ("highlights", 1, "zh"))


def test_fields_come_from_variant_base_or_override():
    a = make().assemble({"sections": {"work": ["acme@short", {"acme-alias": {"location": "Paris"}}]}}, "en")
    at = ("cv", "sections", "Work")
    assert a.source_of(at + (0, "highlights", 0)) == Source("entry", "acme@short", ("highlights", 0, "en"))
    assert a.source_of(at + (0, "company")) == Source("entry", "acme", ("company", "en"))
    assert a.source_of(at + (1, "position")) == Source("entry", "acme-alias", ("position",))
    assert a.source_of(at + (1, "location")) == Source("target", "work", (1, "acme-alias", "location"))


def test_missing_field_falls_back_to_the_entry():
    a = make().assemble({"sections": {"work": [{"company": "Solo"}]}}, "en")
    assert a.source_of(("cv", "sections", "Work", 0, "position")) == Source("target", "work", (0,))


def test_header_design_and_title():
    design = {"languages": {"en": "english", "zh": "mandarin_chinese"},
              "design": {"page": {"size": "a4"}}, "zh": {"page": {"size": "a5"}}}
    a = make(design=design).assemble({"sections": {"work": ["acme"]}}, "zh")
    assert a.source_of(("cv", "name")) == Source("header", None, ("name", "zh"))
    assert a.source_of(("cv", "sections", "工作")) == Source("target", "work")
    assert a.source_of(("design", "page", "size")) == Source("design", "zh", ("page", "size"))
    assert a.source_of(("locale", "language")) == Source("design", None, ("languages", "zh"))
