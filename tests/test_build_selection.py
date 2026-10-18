"""Choosing targets to build."""

import pytest

from prismcv.build import BuildError, Folder
from prismcv.init import create


@pytest.fixture
def folder(tmp_path):
    create(tmp_path, example=True)
    jobs = tmp_path / "targets" / "jobs"
    (jobs / "2026-11-01_other.yaml").write_text((jobs / "2026-10-15_example-data-engineer.yaml").read_text())
    return Folder(tmp_path)


def test_select_by_name_folder_and_glob(folder):
    assert folder.select(["industry"]) == ["industry"]
    assert folder.select(["targets/industry.yaml"]) == ["industry"]
    assert folder.select(["jobs/"]) == ["jobs/2026-10-15_example-data-engineer", "jobs/2026-11-01_other"]
    assert folder.select(["jobs/2026-10*"]) == ["jobs/2026-10-15_example-data-engineer"]
    assert folder.select(["full", "full", "*"]) == ["full", "academic", "industry"]


def test_unknown_selection_is_an_error(folder):
    with pytest.raises(BuildError, match="no such target or folder"):
        folder.select(["nope"])
    with pytest.raises(BuildError, match="no targets match"):
        folder.select(["jobs/1999*"])
