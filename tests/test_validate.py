from prismcv import Source, validate

from test_core import ENTRIES, make


def test_valid_input_has_no_issues(example):
    folder, cv = example
    assert validate(cv.assemble(folder.target("full"), "zh")) == []


def test_issues_point_at_sources():
    entries = dict(ENTRIES, acme=dict(ENTRIES["acme"], start_date="2024-13"))
    cv = make(entries, header={"name": "Ann", "email": "nope"}, titles={"work": "Work"},
              design={"languages": {"en": "english", "zh": "mandarin_chinese"},
                      "design": {"theme": "classic", "page": {"size": "a9"}}})
    issues = {i.source: i.message for i in validate(cv.assemble({"sections": {"work": ["acme"]}}, "en"))}
    assert Source("header", None, ("email",)) in issues
    assert Source("entry", "acme", ("start_date",)) in issues
    assert Source("design", None, ("design", "page", "size")) in issues
    # Only the precise problems, not the section-level summary above them.
    assert len(issues) == 3


def test_missing_required_field_points_at_the_item():
    cv = make(header={"name": "Ann"}, titles={"work": "Work"})
    issues = validate(cv.assemble({"sections": {"work": [{"company": "Solo", "start_date": "2024"}]}}, "en"))
    assert [i.source for i in issues] == [Source("target", "work", (0,))]
    assert "position" in issues[0].location
