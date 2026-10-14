"""Build CV PDFs from a CV folder (cv.yaml, design.yaml, content/, targets/)."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import yaml
from pypdf import PdfReader

from .core import CV, PrismError, Source, max_pages, target_languages
from .render import RenderError, render
from .validate import validate


class BuildError(Exception):
    pass


def load_yaml(path: Path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class Folder:
    """A CV folder on disk: reads it into a CV and names files in messages."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.cv_file, self.design_file = self.root / "cv.yaml", self.root / "design.yaml"
        self.content, self.targets_dir = self.root / "content", self.root / "targets"
        self.out = self.root / "out"
        if not all(p.is_file() for p in (self.cv_file, self.design_file)) \
                or not all(p.is_dir() for p in (self.content, self.targets_dir)):
            raise BuildError(f"{self.root} is not a CV folder: it needs cv.yaml, design.yaml, content/ "
                             "and targets/ (create one with prismcv init)")
        self.where: dict[str, Path] = {}

    def rel(self, path: Path) -> str:
        return str(path.relative_to(self.root))

    def load(self) -> CV:
        entries = {}
        for path in sorted(self.content.rglob("*.yaml")):
            data = load_yaml(path) or {}
            if not isinstance(data, dict):
                raise BuildError(f"{self.rel(path)}: top level must map ids to entries")
            for eid, entry in data.items():
                if eid in entries:
                    raise BuildError(f"duplicate id '{eid}' in {self.rel(self.where[eid])} and {self.rel(path)}")
                entries[eid], self.where[eid] = entry, path
        try:
            return CV(load_yaml(self.cv_file), load_yaml(self.design_file), entries)
        except PrismError as e:
            raise BuildError(self.explain(e)) from None

    # Targets

    def targets(self) -> list[str]:
        return sorted(str(p.relative_to(self.targets_dir).with_suffix("")) for p in self.targets_dir.rglob("*.yaml"))

    def normalise(self, name: str) -> str:
        name = name.removeprefix("targets/").removesuffix(".yaml")
        if not (self.targets_dir / f"{name}.yaml").exists():
            raise BuildError(f"no such target: targets/{name}.yaml")
        return name

    def target(self, name: str) -> dict:
        data = load_yaml(self.targets_dir / f"{name}.yaml") or {}
        if not isinstance(data, dict):
            raise BuildError(f"targets/{name}.yaml: top level must be a mapping")
        return data

    # Messages

    def describe(self, source: Source | None, target: str | None = None) -> str:
        """Where a source is, in the user's files: e.g. content/experience.yaml: acme.highlights[1]."""
        if source is None:
            return f"targets/{target}.yaml" if target else ""
        path = source.path
        if source.kind == "header":
            return "cv.yaml: header" + dotted(path)
        if source.kind == "title":
            return f"cv.yaml: sections.{source.key}" + dotted(path)
        if source.kind == "design":
            return "design.yaml: " + ((source.key or "") + dotted(path)).lstrip(".")
        if source.kind == "entry":
            file = self.rel(self.where[source.key]) if source.key in self.where else "content"
            return f"{file}: {source.key}" + dotted(path)
        return f"targets/{target}.yaml: " + ((source.key or "") + dotted(path)).lstrip(".")

    def explain(self, error: PrismError, target: str | None = None) -> str:
        lines = []
        for issue in error.issues:
            where = self.describe(issue.source, target)
            lines.append(f"{where}: {issue.message}" if where else issue.message)
        return "\n    ".join(lines)


def dotted(path: tuple) -> str:
    return "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in path)


def build(folder: Folder, cv: CV, name: str, only_lang: str | None, debug: bool) -> list[str]:
    """Build one target and return any warnings."""
    target = folder.target(name)
    try:
        langs = target_languages(target, cv)
        limit = max_pages(target)
    except PrismError as e:
        raise BuildError(folder.explain(e, name)) from None
    if only_lang:
        langs = [l for l in langs if l == only_lang]
        if not langs:
            print(f"  - skipped: this target is not built in '{only_lang}'")

    warnings = []
    for lang in langs:
        try:
            assembled = cv.assemble(target, lang)
            issues = validate(assembled)
            if issues:
                raise PrismError(issues)
        except PrismError as e:
            raise BuildError(folder.explain(e, name)) from None

        out_folder = folder.out / name
        out_folder.mkdir(parents=True, exist_ok=True)
        stem = cv.file_stem(lang)
        pdf = out_folder / f"{stem}.pdf"
        with tempfile.TemporaryDirectory(prefix="cv-") as tmp:
            work = Path(tmp)
            try:
                render(assembled.doc, work, stem)
            except RenderError as e:
                raise BuildError(str(e)) from None
            finally:
                if debug:
                    for suffix in (".yaml", ".typ"):
                        if (work / f"{stem}{suffix}").exists():
                            shutil.copy2(work / f"{stem}{suffix}", out_folder / f"{stem}{suffix}")
            shutil.copy2(work / f"{stem}.pdf", pdf)

        pages = len(PdfReader(pdf).pages)
        print(f"  ✓ {folder.rel(pdf)}  ({pages} page{'s' if pages != 1 else ''})")
        if limit and pages > limit:
            warnings.append(f"{name} ({lang}): {pages} pages, exceeds max_pages: {limit}")
    return warnings
