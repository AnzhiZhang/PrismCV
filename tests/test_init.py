"""Creating a CV folder from the template or an example."""

import pytest

from prismcv.init import InitError, create


@pytest.mark.parametrize("example, first", [
    (False, "cv.yaml"),
    (True, "content/education.yaml"),
    ("rendercv", "content/achievements.yaml"),
])
def test_create_copies_the_chosen_source(tmp_path, example, first):
    created = [p.relative_to(tmp_path).as_posix() for p in create(tmp_path, example=example)]
    assert first in created
    assert ".gitignore" in created


def test_unknown_example_is_rejected(tmp_path):
    with pytest.raises(InitError, match="unknown example 'nope'"):
        create(tmp_path, example="nope")
