import pytest
from test_portability import example_files

from prismcv import CV, PrismError, Source, read_files, write_files

LANGS = {"en": "english", "zh": "mandarin_chinese"}


def make(file_name=None):
    design = {"languages": LANGS}
    if file_name is not None:
        design = {"file_name": file_name, **design}
    return CV({"header": {"name": "Ann (Annie) Lee"}}, design, {})


def test_default_comes_from_the_name():
    assert make().file_stem("zh") == "Ann_Annie_Lee_CV_zh"


def test_template_fills_lang_and_target():
    cv = make("Ann_Lee_{target}_{lang}")
    assert cv.file_stems({}, "jobs/2026-10-15_acme", ["en", "zh"]) == {
        "en": "Ann_Lee_jobs-2026-10-15_acme_en",
        "zh": "Ann_Lee_jobs-2026-10-15_acme_zh",
    }


def test_target_overrides_design():
    cv = make("Ann_Lee_CV_{lang}")
    assert cv.file_stem("en", {"file_name": "Ann_Lee_Resume"}, "industry") == "Ann_Lee_Resume"


def test_one_name_for_one_language_is_fine():
    cv = make("Ann_Lee_CV")
    assert cv.file_stems({"langs": ["en"]}, "industry", ["en"]) == {"en": "Ann_Lee_CV"}


def test_same_name_for_two_languages_is_an_error():
    with pytest.raises(PrismError, match="add {lang}") as e:
        make("Ann_Lee_CV").file_stems({}, "full", ["en", "zh"])
    assert e.value.issues[0].source == Source("design", None, ("file_name",))
    with pytest.raises(PrismError, match="add {lang}") as e:
        make().file_stems({"file_name": "Ann_Resume"}, "full", ["en", "zh"])
    assert e.value.issues[0].source == Source("target", None, ("file_name",))


@pytest.mark.parametrize("bad, message", [
    ("Ann_{name}_{lang}", "not {name}"),
    ("out/Ann_{lang}", "cannot contain"),
    ("Ann_{lang}.pdf", "without .pdf"),
    ("", "must be text"),
    (5, "must be text"),
])
def test_bad_templates_are_reported(bad, message):
    with pytest.raises(PrismError, match=message):
        make(bad)
    with pytest.raises(PrismError, match=message):
        make().file_stem("en", {"file_name": bad}, "full")


def test_file_name_is_not_sent_to_rendercv():
    doc = make("Ann_{lang}").assemble({"sections": {}}, "en").doc
    assert "file_name" not in doc


def test_file_name_round_trips_and_is_written_first():
    files = example_files()
    parsed = read_files(files)
    assert parsed.design["file_name"] == "Nathan_Lee_CV_{lang}"
    written = write_files(parsed)
    assert written["design.yaml"].splitlines()[0] == "file_name: Nathan_Lee_CV_{lang}"
    assert read_files(written) == parsed
