from pathlib import Path

import pytest

from prismcv.build import Folder

EXAMPLE = Path(__file__).resolve().parents[1] / "src" / "prismcv" / "example"


@pytest.fixture
def example():
    """The example CV folder, loaded."""
    folder = Folder(EXAMPLE)
    return folder, folder.load()
