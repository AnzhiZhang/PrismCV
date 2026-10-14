"""Create a new CV folder from the template."""

from __future__ import annotations

import shutil
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent / "template"
CV_PARTS = ("cv.yaml", "design.yaml", "content", "targets")


class InitError(Exception):
    pass


def create(root: Path) -> list[Path]:
    """Copy the template into root, refusing to overwrite an existing CV. Returns the files created."""
    root = root.resolve()
    existing = [name for name in CV_PARTS if (root / name).exists()]
    if existing:
        raise InitError(f"{root} already contains {', '.join(existing)}")
    root.mkdir(parents=True, exist_ok=True)
    created = []
    for src in sorted(TEMPLATE.rglob("*")):
        if src.is_dir() or src.name == "__pycache__":
            continue
        rel = src.relative_to(TEMPLATE)
        name = "." + rel.name[4:] if rel.name.startswith("dot-") else rel.name
        dest = root / rel.parent / name
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        created.append(dest)
    return created
