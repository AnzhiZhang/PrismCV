"""Text must appear in the PDF exactly as written, apart from bold, italic and links."""

import shutil

import pytest
from pypdf import PdfReader

from prismcv import CV, literal
from prismcv.render import render

TRICKY = [
    "Hash #hash, C# and #1",
    "A Typst call #set text(red) and #emph[x]",
    "Dollars $100 and $$x$$",
    "At @user and <label> and </b> and a < b",
    "Backslash \\ and brackets [a] and tilde ~ and caret ^",
    "Range 2020 - 2021 inside a bullet",
    "snake_case_name and 100% and \"quotes\"",
    "!!! not an admonition",
]


def test_literal_keeps_link_targets():
    s = "See [#notes](https://example.com/#notes) - #now"
    out = literal(s)
    assert "(https://example.com/#notes)" in out
    assert "#⁠now" in out and " - " in out


def test_literal_leaves_ordinary_text_alone():
    for s in ["Plain text", "Python, C++ and C#", "**bold** and *italic*", "Score 5 > 3", "2020–2021"]:
        assert literal(s) == s


def test_non_prose_fields_are_not_changed():
    cv = CV({"header": {"name": "A #b", "website": "https://a.com/#x"}}, {"languages": {"en": "english"}}, {})
    doc = cv.assemble({"sections": {}}, "en", literal=True).doc
    assert doc["cv"]["website"] == "https://a.com/#x"
    assert doc["cv"]["name"] == "A #⁠b"


@pytest.mark.skipif(shutil.which("rendercv") is None and not __import__("importlib").util.find_spec("rendercv"),
                    reason="RenderCV is not installed")
def test_tricky_text_appears_literally_in_the_pdf(tmp_path):
    entries = {"job": {"company": "Acme #corp <x>", "position": "Dev [lead]", "start_date": "2025-01",
                       "highlights": TRICKY}}
    cv = CV({"header": {"name": "Test"}, "sections": {"work": "Work"}},
            {"languages": {"en": "english"}, "design": {"theme": "classic"}}, entries)
    doc = cv.assemble({"sections": {"work": ["job"]}}, "en", literal=True).doc
    pdf = render(doc, tmp_path, "t")
    text = " ".join(page.extract_text() for page in PdfReader(pdf).pages)
    text = " ".join(text.replace("⁠", "").replace(" ", " ").split())
    for s in TRICKY + ["Acme #corp <x>", "Dev [lead]"]:
        assert " ".join(s.split()) in text, s
