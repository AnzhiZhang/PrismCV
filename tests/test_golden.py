"""The assembled RenderCV input for each example must not change unless meant to.

To accept an intended change, regenerate the files in tests/golden/ with:
python tests/test_golden.py
"""

import json
import sys
from pathlib import Path

import pytest

from prismcv.build import Folder
from prismcv.init import EXAMPLES

GOLDEN = Path(__file__).parent / "golden"
# The default example keeps its original file name.
FILES = {"default": "example.json", "rendercv": "example-rendercv.json"}


def assemble_all(folder, cv) -> dict:
    result = {}
    for name in folder.targets():
        target = folder.target(name)
        for lang in target.get("langs") or list(cv.languages):
            result[f"{name}|{lang}"] = cv.assemble(target, lang).doc
    result["_stem"] = {lang: cv.file_stem(lang) for lang in cv.languages}
    return json.loads(json.dumps(result, ensure_ascii=False, default=str))


@pytest.mark.parametrize("name", EXAMPLES)
def test_example_matches_golden(name):
    folder = Folder(EXAMPLES[name])
    expected = json.loads((GOLDEN / FILES[name]).read_text(encoding="utf-8"))
    actual = assemble_all(folder, folder.load())
    assert actual.keys() == expected.keys()
    for k in expected:
        # Compare as text too, so key order counts.
        assert json.dumps(actual[k], ensure_ascii=False) == json.dumps(expected[k], ensure_ascii=False), k


if __name__ == "__main__":
    for name, path in EXAMPLES.items():
        folder = Folder(path)
        (GOLDEN / FILES[name]).write_text(
            json.dumps(assemble_all(folder, folder.load()), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
