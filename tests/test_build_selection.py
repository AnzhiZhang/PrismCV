"""Choosing targets to build, archived targets, and skipping unchanged PDFs."""

import pytest

from prismcv.build import BuildError, Folder, build
from prismcv.init import create


@pytest.fixture
def folder(tmp_path):
    create(tmp_path, example=True)
    jobs = tmp_path / "targets" / "jobs"
    (jobs / "2026-11-01_other.yaml").write_text((jobs / "2026-10-15_example-data-engineer.yaml").read_text())
    archive = tmp_path / "targets" / "archive"
    archive.mkdir()
    (archive / "old.yaml").write_text("langs: [en]\nsections:\n  education: [meng]\n")
    return Folder(tmp_path)


def test_all_leaves_out_archive(folder):
    assert "archive/old" not in folder.targets()
    assert "archive/old" in folder.targets(archived=True)


def test_select_by_name_folder_and_glob(folder):
    assert folder.select(["industry"]) == ["industry"]
    assert folder.select(["targets/industry.yaml"]) == ["industry"]
    assert folder.select(["jobs/"]) == ["jobs/2026-10-15_example-data-engineer", "jobs/2026-11-01_other"]
    assert folder.select(["jobs/2026-10*"]) == ["jobs/2026-10-15_example-data-engineer"]
    assert folder.select(["full", "full", "*"]) == ["full", "academic", "industry"]


def test_only_targets_archive_is_archived(folder):
    nested = folder.targets_dir / "jobs" / "archive"
    nested.mkdir()
    (nested / "kept.yaml").write_text("langs: [en]\nsections:\n  education: [meng]\n")
    assert "jobs/archive/kept" in folder.targets()
    assert "jobs/archive/kept" in folder.select(["jobs"])


def test_archive_only_when_asked(folder):
    assert "archive/old" not in folder.select(["*", "*/*"])
    assert folder.select(["archive"]) == ["archive/old"]
    assert folder.select(["archive/old"]) == ["archive/old"]


def test_unknown_selection_is_an_error(folder):
    with pytest.raises(BuildError, match="no such target or folder"):
        folder.select(["nope"])
    with pytest.raises(BuildError, match="no targets match"):
        folder.select(["jobs/1999*"])


def test_unchanged_pdfs_are_skipped(folder, capsys):
    cv = folder.load()
    cache = {}
    build(folder, cv, "industry", "en", False, cache=cache)
    assert "✓" in capsys.readouterr().out and cache
    build(folder, cv, "industry", "en", False, cache=cache)
    assert "unchanged" in capsys.readouterr().out
    build(folder, cv, "industry", "en", False, force=True, cache=cache)
    assert "✓" in capsys.readouterr().out

    # A change to the content renders again.
    cv.header["name"] = "Someone Else"
    build(folder, cv, "industry", "en", False, cache=cache)
    assert "✓" in capsys.readouterr().out

    # A missing PDF renders again even if nothing changed.
    for pdf in (folder.out / "industry").glob("*.pdf"):
        pdf.unlink()
    build(folder, cv, "industry", "en", False, cache=cache)
    assert "✓" in capsys.readouterr().out


def test_cache_is_shared_in_out(folder):
    folder.write_cache({"industry|en": "x"})
    assert (folder.out / ".prismcv-build.json").is_file()
    assert folder.read_cache() == {"industry|en": "x"}
