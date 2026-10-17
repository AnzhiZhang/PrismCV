from pathlib import Path

import pytest

from prismcv import FilesError, read_files, write_files

EXAMPLE = Path(__file__).parents[1] / "src" / "prismcv" / "example"


def example_files() -> dict[str, str]:
    return {
        str(path.relative_to(EXAMPLE)): path.read_text(encoding="utf-8")
        for path in EXAMPLE.rglob("*.yaml")
    }


def test_example_round_trips_as_data() -> None:
    parsed = read_files(example_files())
    assert [item["code"] for item in parsed["languages"]] == ["en", "zh"]
    assert any(item["name"].startswith("jobs/") for item in parsed["targets"])
    assert read_files(write_files(parsed)) == parsed


def test_duplicate_entries_are_rejected() -> None:
    files = example_files()
    files["content/duplicate.yaml"] = "meng: {institution: Elsewhere}\n"
    with pytest.raises(FilesError, match="duplicate"):
        read_files(files)


def test_unknown_target_references_are_rejected() -> None:
    files = example_files()
    files["targets/broken.yaml"] = "sections: {work: [missing]}\n"
    with pytest.raises(FilesError):
        read_files(files)


def test_unsafe_paths_are_rejected() -> None:
    with pytest.raises(FilesError, match="unsafe"):
        read_files({"../cv.yaml": "{}"})
