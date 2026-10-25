"""Document conversion with real RenderCV models/templates and synthetic content."""

import copy
import json
import urllib.request

import pytest
import yaml
from rendercv.renderer.templater import templater
from rendercv.renderer.templater.templater import get_jinja2_environment
from rendercv.renderer.typst import generate_typst
from rendercv.schema import rendercv_model_builder as builder
from rendercv.schema.models.design.built_in_design import available_themes
from rendercv.schema.rendercv_model_builder import (
    build_rendercv_model_from_commented_map,
)

from prismcv import CV, CVData, Entry, PrismError, Source, Target, validate
from prismcv.render import render


def synthetic_data():
    return CVData(
        header={"name": {"en": "Synthetic Example", "zh": "合成示例"}},
        section_titles={"work": {"en": "Work", "zh": "工作"}},
        languages={"en": "english", "zh": "mandarin_chinese"},
        design={
            "design": {"theme": "classic"},
            "settings": {"current_date": "2026-10-25"},
        },
        entries=[
            Entry(
                "job",
                "content/work",
                {
                    "company": "Example",
                    "position": "Engineer",
                    "start_date": "2024-01",
                    "highlights": [
                        {
                            "id": "keep",
                            "text": {
                                "en": "Keep #literal {x} - **bold**",
                                "zh": "保留 #原文 {x} - **粗体**",
                            },
                        },
                        {"id": "hide", "text": "Hidden bullet"},
                    ],
                },
            ),
            Entry("job@lead", "content/work", {"position": "Lead"}),
        ],
        targets=[
            Target(
                "industry", {"sections": {"work": [{"job@lead": {"hide": ["hide"]}}]}}
            )
        ],
    )


def assemble(data=None, lang="en", literal=True):
    data = data or synthetic_data()
    return CV.from_data(data).assemble(data.targets[0].data, lang, literal=literal)


def test_exports_preserve_values_order_and_isolate_nested_data():
    document = assemble(literal=False)
    strings = [
        "中文标点，冒号: hash # comma, braces { en: x }",
        "Quotes 'single' and \"double\", [brackets], \\backslash",
        "First line\nSecond line: # {still text}\n",
        "2026-10-25",
        "true",
        "null",
        "  leading and trailing  ",
    ]
    document.doc["cv"]["sections"]["Work"][0]["highlights"] = strings
    document.doc["cv"]["sections"]["Second"] = ["Another section"]
    before = copy.deepcopy(document)
    exported = document.to_dict()
    assert json.dumps(exported, ensure_ascii=False) == json.dumps(
        document.doc, ensure_ascii=False
    )
    exported["cv"]["sections"]["Work"][0]["highlights"].append("changed")
    exported["settings"]["current_date"] = "2000-01-01"
    text = document.to_yaml()
    assert "中文标点" in text
    assert json.dumps(yaml.safe_load(text), ensure_ascii=False) == json.dumps(
        document.doc, ensure_ascii=False
    )
    assert document == before
    assert "sources" not in exported
    assert "render_command" not in document.to_dict()["settings"]


@pytest.mark.parametrize(
    "case, expected_source",
    [
        ("entry", Source("entry", "job", ("start_date",))),
        ("header", Source("header", None, ("email",))),
        ("item", Source("target", "work", (0,))),
        # RenderCV reports an invalid locale discriminator on the enclosing object.
        ("locale", Source("design", None, ("locale",))),
        ("design", Source("design", None, ("design", "page", "size"))),
        ("variant", Source("entry", "job@lead", ("position",))),
        ("override", Source("target", "work", (0, "job@lead", "start_date"))),
    ],
)
def test_validation_and_conversion_share_source_mapped_errors(case, expected_source):
    data = synthetic_data()
    if case == "entry":
        data.entries[0].fields["start_date"] = "2024-13"
    elif case == "header":
        data.header["email"] = "invalid"
    elif case == "item":
        data.targets[0].data["sections"]["work"] = [{"company": "Example"}]
    elif case == "locale":
        data.languages["en"] = "invalid"
    elif case == "design":
        data.design["design"]["page"] = {"size": "a9"}
    elif case == "variant":
        data.entries[1].fields["position"] = 42
    else:
        data.targets[0].data["sections"]["work"][0]["job@lead"][
            "start_date"
        ] = "2024-13"
    document = assemble(data)
    before = copy.deepcopy(document)
    issues = validate(document)
    assert issues and document.validate() == issues
    assert any(i.source == expected_source and i.location for i in issues)
    with pytest.raises(PrismError) as exc:
        document.to_typst()
    assert exc.value.issues == issues
    assert document == before


def test_repeated_calls_and_edits_do_not_cache_or_mutate_inputs():
    data = synthetic_data()
    before_data = copy.deepcopy(data)
    cv = CV.from_data(data)
    before_cv = copy.deepcopy(vars(cv))
    document = cv.assemble(data.targets[0].data, "en", literal=True)
    before = copy.deepcopy(document)
    assert document.validate() == []
    first = document.to_typst()
    assert first == document.to_typst()
    assert document == before and data == before_data and vars(cv) == before_cv
    document.doc["design"]["page"] = {"size": "a4"}
    assert 'page-size: "a4"' in document.to_typst()
    assert document.to_typst() != first
    document.doc["cv"]["sections"]["Work"][0]["start_date"] = "2024-13"
    assert document.validate()[0].source == Source("entry", "job", ("start_date",))
    with pytest.raises(PrismError) as exc:
        document.to_typst()
    assert exc.value.issues == document.validate()
    document.doc["cv"]["sections"]["Work"][0]["start_date"] = "2024-01"
    document.doc["cv"]["email"] = "invalid"
    assert document.validate()[0].source is None
    assert document.validate()[0].location == ("cv", "email")
    assert document.sources == before.sources


@pytest.mark.parametrize("theme", available_themes)
@pytest.mark.parametrize("lang", ["en", "zh"])
def test_real_templates_match_rendercv_file_generation(tmp_path, theme, lang):
    document = assemble(lang=lang)
    document.doc["design"]["theme"] = theme
    document.doc["settings"]["render_command"] = {
        "typst_path": str(tmp_path / "reference.typ")
    }
    before = copy.deepcopy(document)
    source = document.to_typst()
    reference = generate_typst(
        build_rendercv_model_from_commented_map(document.to_dict())
    )
    assert source.encode() == reference.read_bytes()
    assert "@preview/rendercv:0.3.0" in source
    assert "Lead" in source and "Hidden bullet" not in source
    assert ("Synthetic Example" if lang == "en" else "合成示例") in source
    assert document == before


def test_nathan_lee_targets_and_languages_use_real_templates(example):
    folder, cv = example
    for name in folder.targets():
        target = folder.target(name)
        for lang in target.get("langs") or cv.languages:
            document = cv.assemble(target, lang, literal=True)
            document.doc.setdefault("settings", {})["current_date"] = "2026-10-25"
            before = copy.deepcopy(document)
            assert document.validate() == []
            assert "@preview/rendercv:0.3.0" in document.to_typst()
            assert document == before


def test_source_matches_existing_cli_generation(tmp_path):
    document = assemble()
    expected = document.to_typst()
    pdf = render(document.doc, tmp_path, "comparison")
    assert pdf.is_file()
    assert (tmp_path / "comparison.typ").read_bytes() == expected.encode()


def test_explicit_source_conversion_ignores_cli_generation_switches():
    document = assemble()
    source = document.to_typst()
    document.doc["settings"]["render_command"] = {
        "dont_generate_typst": True,
        "dont_generate_pdf": True,
    }
    assert document.to_typst() == source


def test_photo_download_failure_is_a_prism_error(tmp_path, monkeypatch):
    document = assemble()
    document.doc["cv"]["photo"] = "https://example.com/synthetic.png"
    document.doc["settings"]["render_command"] = {
        "output_folder": str(tmp_path / "assets")
    }
    before = copy.deepcopy(document)

    def failed_download(*args):
        raise OSError("synthetic download failure")

    monkeypatch.setattr(urllib.request, "urlretrieve", failed_download)
    with pytest.raises(
        PrismError, match="Failed to download photo.*synthetic download failure"
    ) as exc:
        document.to_typst()
    assert exc.value.issues[0].source is None
    assert document == before


def test_local_template_override(tmp_path, monkeypatch):
    theme_dir = tmp_path / "classic"
    theme_dir.mkdir()
    (theme_dir / "Header.j2.typ").write_text("LOCAL_TEMPLATE {{ cv._plain_name }}")
    document = assemble()
    before = copy.deepcopy(document)
    monkeypatch.chdir(tmp_path)
    get_jinja2_environment.cache_clear()
    try:
        assert "LOCAL_TEMPLATE Synthetic Example" in document.to_typst()
        assert document == before
    finally:
        get_jinja2_environment.cache_clear()


def test_template_failure_is_diagnostic_without_inventing_a_source(monkeypatch):
    def broken_template(*args):
        raise RuntimeError("synthetic template failure")

    monkeypatch.setattr(templater, "render_full_template", broken_template)
    with pytest.raises(
        PrismError,
        match="RenderCV could not generate Typst: RuntimeError: synthetic template failure",
    ) as exc:
        assemble().to_typst()
    assert exc.value.issues[0].source is None
    assert exc.value.issues[0].location == ()


def test_model_failures_share_existing_diagnostics(monkeypatch):
    def broken_builder(*args):
        raise RuntimeError("synthetic model failure")

    monkeypatch.setattr(
        builder, "build_rendercv_model_from_commented_map", broken_builder
    )
    document = assemble()
    issues = document.validate()
    assert issues == validate(document)
    assert "RenderCV could not check this CV" in issues[0].message
    with pytest.raises(PrismError) as exc:
        document.to_typst()
    assert exc.value.issues == issues
