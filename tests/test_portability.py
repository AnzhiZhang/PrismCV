from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from test_golden import assemble_all

from prismcv import (
    CV,
    CVData,
    Entry,
    FilesError,
    Target,
    read_files,
    target_languages,
    write_files,
)
from prismcv.build import Folder

EXAMPLE = Path(__file__).parents[1] / "src" / "prismcv" / "example"


def example_files() -> dict[str, str]:
    return {
        str(path.relative_to(EXAMPLE)): path.read_text(encoding="utf-8")
        for path in EXAMPLE.rglob("*.yaml")
    }


def test_example_round_trips_as_typed_data() -> None:
    parsed = read_files(example_files())
    assert isinstance(parsed, CVData)
    assert parsed.languages == {"en": "english", "zh": "mandarin_chinese"}
    assert all(isinstance(item, Entry) for item in parsed.entries)
    assert all(isinstance(item, Target) for item in parsed.targets)
    assert any(item.name.startswith("jobs/") for item in parsed.targets)
    assert read_files(write_files(parsed)) == parsed


def test_cv_from_data_is_equivalent_to_file_shaped_constructor() -> None:
    files = example_files()
    data = read_files(files)
    cv_doc = yaml.safe_load(files["cv.yaml"])
    design_doc = yaml.safe_load(files["design.yaml"])
    entries = {entry.id: entry.fields for entry in data.entries}
    direct = CV(cv_doc, design_doc, entries)
    typed = CV.from_data(data)

    assert typed.languages == direct.languages
    for target in data.targets:
        langs = target_languages(target.data, direct)
        assert typed.file_stems(target.data, target.name, langs) == direct.file_stems(
            target.data, target.name, langs
        )
        for lang in langs:
            assert typed.assemble(target.data, lang) == direct.assemble(
                target.data, lang
            )


def test_exported_example_builds_identically(tmp_path: Path) -> None:
    original = Folder(EXAMPLE)
    expected = assemble_all(original, original.load())
    for name, text in write_files(read_files(example_files())).items():
        _write(tmp_path, name, text)

    exported = Folder(tmp_path)

    assert assemble_all(exported, exported.load()) == expected


def test_write_files_uses_readable_ordered_and_safe_yaml() -> None:
    data = CVData(
        header={
            "name": {"zh": "艾达", "en": "Ada"},
            "location": {"zh": "英国伦敦", "en": "London, UK"},
            "summary": {
                "zh": "这是一段足够长的中文说明，用来确认较长的多语言内容会使用多行格式。",
                "en": "A deliberately long summary that should not be squeezed into one flow mapping line.",
            },
        },
        section_titles={"work": {"zh": "经历", "en": "Work"}},
        languages={"en": "english", "zh": "mandarin_chinese"},
        design={"design": {"theme": "classic"}, "file_name": "Ada_CV_{lang}"},
        entries=[],
        targets=[],
    )

    files = write_files(data)

    assert files["design.yaml"].startswith("file_name: Ada_CV_{lang}\n\nlanguages:")
    assert "languages:\n  en: english\n  zh: mandarin_chinese" in files["design.yaml"]
    assert files["cv.yaml"].startswith("header:\n")
    assert "\nsections:\n" in files["cv.yaml"]
    assert "name: { en: Ada, zh: 艾达 }" in files["cv.yaml"]
    assert 'location: { en: "London, UK", zh: 英国伦敦 }' in files["cv.yaml"]
    assert "summary:\n    en:" in files["cv.yaml"]
    assert yaml.safe_load(files["cv.yaml"])["header"]["location"]["en"] == "London, UK"


def test_bullet_ids_and_target_hide_round_trip() -> None:
    files = example_files()
    files["content/identified.yaml"] = (
        "job:\n  company: Acme\n  position: Engineer\n  highlights:\n"
        "    - { id: shipped, text: Shipped it }\n"
    )
    files["targets/identified.yaml"] = (
        "langs: [en]\nsections:\n  work:\n    - job: { hide: [shipped] }\n"
    )
    data = read_files(files)

    written = write_files(data)

    assert (
        yaml.safe_load(written["content/identified.yaml"])["job"]["highlights"][0]["id"]
        == "shipped"
    )
    target = yaml.safe_load(written["targets/identified.yaml"])
    assert target["sections"]["work"][0]["job"]["hide"] == ["shipped"]
    assert read_files(written) == data


def test_duplicate_entries_name_both_files() -> None:
    files = example_files()
    files["content/duplicate.yaml"] = "meng: {institution: Elsewhere}\n"
    with pytest.raises(
        FilesError,
        match=r"duplicate id 'meng' in content/duplicate.yaml and content/education.yaml",
    ):
        read_files(files)


def test_unknown_target_references_are_rejected_with_location() -> None:
    files = example_files()
    files["targets/broken.yaml"] = "sections: {work: [missing]}\n"
    with pytest.raises(
        FilesError, match=r"targets/broken.yaml: work\[0\]: unknown id 'missing'"
    ):
        read_files(files)


def test_unsafe_paths_are_rejected() -> None:
    with pytest.raises(FilesError, match="unsafe"):
        read_files({"../cv.yaml": "{}"})


def _write(root: Path, name: str, value) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        value if isinstance(value, str) else yaml.safe_dump(value, sort_keys=False),
        encoding="utf-8",
    )


def _cli_folder(root: Path) -> None:
    _write(
        root,
        "cv.yaml",
        {"header": {"name": {"en": "Ada", "zh": "艾达"}}, "sections": {"work": "Work"}},
    )
    _write(
        root,
        "design.yaml",
        {
            "file_name": "Ada_CV_{lang}",
            "languages": {"en": "english", "zh": "mandarin_chinese"},
        },
    )
    _write(
        root,
        "content/work.yaml",
        {
            "job": {
                "company": {"en": "Acme", "zh": "艾克米"},
                "position": "Engineer",
                "start_date": "2025-01",
            }
        },
    )
    _write(root, "targets/industry.yaml", {"sections": {"work": ["job"]}})


def _run_cli(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "prismcv.cli", "build", "industry", "--root", str(root)],
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        (
            "duplicate",
            "✗ duplicate id 'job' in content/other.yaml and content/work.yaml",
        ),
        ("unknown", "✗ targets/industry.yaml: work[0]: unknown id 'missing'"),
        ("translation", "✗ content/work.yaml: job.company: missing 'zh' text"),
        (
            "date",
            "content/work.yaml: job.start_date: The month must be between 1 and 12.",
        ),
        (
            "file_name",
            '✗ design.yaml: file_name: cannot contain braces outside {lang} and {target}, or any of \\ / : * ? " < > |',
        ),
    ],
)
def test_cli_errors_keep_file_and_field_locations(
    tmp_path: Path, case: str, expected: str
) -> None:
    _cli_folder(tmp_path)
    if case == "duplicate":
        _write(tmp_path, "content/other.yaml", {"job": {"company": "Other"}})
    elif case == "unknown":
        _write(tmp_path, "targets/industry.yaml", {"sections": {"work": ["missing"]}})
    elif case == "translation":
        _write(
            tmp_path,
            "content/work.yaml",
            {"job": {"company": {"en": "Acme"}, "position": "Engineer"}},
        )
    elif case == "date":
        _write(
            tmp_path,
            "content/work.yaml",
            {
                "job": {
                    "company": "Acme",
                    "position": "Engineer",
                    "start_date": "2025-99",
                }
            },
        )
    else:
        _write(
            tmp_path,
            "design.yaml",
            {
                "file_name": "out/Ada_{lang}",
                "languages": {"en": "english", "zh": "mandarin_chinese"},
            },
        )

    result = _run_cli(tmp_path)

    assert result.returncode == 1
    assert expected in result.stderr
    assert "Traceback" not in result.stderr
