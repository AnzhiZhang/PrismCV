"""Build CV PDFs from a CV folder (cv.yaml, design.yaml, content/, targets/)."""

from __future__ import annotations

import fnmatch
import shutil
import tempfile
from pathlib import Path

import yaml
from pypdf import PdfReader

from .core import CV, PrismError, explain, max_pages, target_languages
from .portability import CVData, FilesError, read_files
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
        self.data: CVData | None = None

    def rel(self, path: Path) -> str:
        return str(path.relative_to(self.root))

    def load(self) -> CV:
        paths = [self.cv_file, self.design_file]
        paths.extend(sorted(self.content.rglob("*.yaml")))
        paths.extend(sorted(self.targets_dir.rglob("*.yaml")))
        files = {self.rel(path): path.read_text(encoding="utf-8") for path in paths}
        try:
            self.data = read_files(files, check=False)
            return CV.from_data(self.data)
        except FilesError as e:
            raise BuildError(str(e)) from None

    # Targets

    def targets(self) -> list[str]:
        return sorted(str(p.relative_to(self.targets_dir).with_suffix("")) for p in self.targets_dir.rglob("*.yaml"))

    def select(self, patterns: list[str]) -> list[str]:
        """Targets named by a target, a folder of targets or a glob, in order and without repeats."""
        every = self.targets()
        chosen: list[str] = []
        for raw in patterns:
            pattern = raw.removeprefix("targets/").removesuffix(".yaml").rstrip("/")
            if pattern in every:
                found = [pattern]
            elif (self.targets_dir / pattern).is_dir():
                found = [n for n in every if n.startswith(pattern + "/")]
            elif any(c in pattern for c in "*?["):
                found = [n for n in every if glob_match(n, pattern)]
            else:
                raise BuildError(f"no such target or folder: targets/{pattern}")
            if not found:
                raise BuildError(f"no targets match {raw}")
            chosen += [n for n in found if n not in chosen]
        return chosen

    def normalise(self, name: str) -> str:
        name = name.removeprefix("targets/").removesuffix(".yaml")
        if not (self.targets_dir / f"{name}.yaml").exists():
            raise BuildError(f"no such target: targets/{name}.yaml")
        return name

    def target(self, name: str) -> dict:
        if self.data is not None:
            target = next((item for item in self.data.targets if item.name == name), None)
            if target is not None:
                return target.data
        data = load_yaml(self.targets_dir / f"{name}.yaml") or {}
        if not isinstance(data, dict):
            raise BuildError(f"targets/{name}.yaml: top level must be a mapping")
        return data

    @property
    def entry_files(self) -> dict[str, str]:
        return {
            entry.id: f"content/{entry.file}.yaml"
            for entry in self.data.entries
        } if self.data else {}


def glob_match(name: str, pattern: str) -> bool:
    """Shell-style matching where * and ? stay within one folder level."""
    parts, wanted = name.split("/"), pattern.split("/")
    return len(parts) == len(wanted) and all(fnmatch.fnmatchcase(p, w) for p, w in zip(parts, wanted))


def build(folder: Folder, cv: CV, name: str, only_lang: str | None, debug: bool) -> list[str]:
    """Build one target and return any warnings."""
    target = folder.target(name)
    try:
        langs = target_languages(target, cv)
        limit = max_pages(target)
        stems = cv.file_stems(target, name, langs)
    except PrismError as e:
        raise BuildError(explain(e, folder.entry_files, name)) from None
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
            raise BuildError(explain(e, folder.entry_files, name)) from None

        out_folder = folder.out / name
        out_folder.mkdir(parents=True, exist_ok=True)
        stem = stems[lang]
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
