"""The assembled RenderCV input for the example must not change unless meant to.

tests/golden/example.json was produced by PrismCV 0.1.1, before the core was
separated from the command line. To accept an intended change, regenerate it
with: python tests/test_golden.py
"""

import json
import sys
from pathlib import Path

GOLDEN = Path(__file__).parent / "golden" / "example.json"


def assemble_all(folder, cv) -> dict:
    result = {}
    for name in folder.targets():
        target = folder.target(name)
        for lang in target.get("langs") or list(cv.languages):
            result[f"{name}|{lang}"] = cv.assemble(target, lang).doc
    result["_stem"] = {lang: cv.file_stem(lang) for lang in cv.languages}
    return json.loads(json.dumps(result, ensure_ascii=False, default=str))


def test_example_matches_golden(example):
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    actual = assemble_all(*example)
    assert actual.keys() == expected.keys()
    for k in expected:
        # Compare as text too, so key order counts.
        assert json.dumps(actual[k], ensure_ascii=False) == json.dumps(expected[k], ensure_ascii=False), k


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    from conftest import EXAMPLE
    from prismcv.build import Folder
    folder = Folder(EXAMPLE)
    GOLDEN.write_text(json.dumps(assemble_all(folder, folder.load()), ensure_ascii=False, indent=1) + "\n",
                      encoding="utf-8")
    print(f"wrote {GOLDEN}")
