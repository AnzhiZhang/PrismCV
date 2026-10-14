"""Create a new CV folder from the template or the example."""

from __future__ import annotations

import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "template"
EXAMPLE = HERE / "example"
CV_PARTS = ("cv.yaml", "design.yaml", "content", "targets")
GITIGNORE = "# Generated PDFs\nout/\n"


class InitError(Exception):
    pass


def create(root: Path, example: bool = False) -> list[Path]:
    """Copy the template (or the example) into root without overwriting a CV. Returns the files created."""
    root = root.resolve()
    existing = [name for name in CV_PARTS if (root / name).exists()]
    if existing:
        raise InitError(f"{root} already contains {', '.join(existing)}")
    source = EXAMPLE if example else TEMPLATE
    created = []
    for src in sorted(source.rglob("*.yaml")):
        dest = root / src.relative_to(source)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        created.append(dest)
    gitignore = root / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(GITIGNORE, encoding="utf-8")
        created.append(gitignore)
    return created
