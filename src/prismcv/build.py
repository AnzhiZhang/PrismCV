"""Build CV PDFs from a CV folder (cv.yaml, design.yaml, content/, targets/)."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import shutil
import tempfile
from importlib.metadata import PackageNotFoundError, version
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

    def targets(self, archived: bool = False) -> list[str]:
        """Every target name; those in targets/archive/ only when archived is set."""
        names = sorted(str(p.relative_to(self.targets_dir).with_suffix("")) for p in self.targets_dir.rglob("*.yaml"))
        return names if archived else [n for n in names if not is_archived(n)]

    def select(self, patterns: list[str]) -> list[str]:
        """Targets named by a target, a folder of targets or a glob, in order and without repeats.

        Folders and globs leave out targets/archive/ unless they point into it.
        """
        every = self.targets(archived=True)
        chosen: list[str] = []
        for raw in patterns:
            pattern = raw.removeprefix("targets/").removesuffix(".yaml").rstrip("/")
            include_archived = is_archived(pattern)
            if pattern in every:
                found = [pattern]
            elif (self.targets_dir / pattern).is_dir():
                found = [n for n in every if n.startswith(pattern + "/")]
            elif any(c in pattern for c in "*?["):
                found = [n for n in every if glob_match(n, pattern)]
            else:
                raise BuildError(f"no such target or folder: targets/{pattern}")
            if not include_archived:
                found = [n for n in found if not is_archived(n)]
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

    # Skipping unchanged PDFs

    @property
    def cache_file(self) -> Path:
        return self.out / ".prismcv-build.json"

    def read_cache(self) -> dict:
        try:
            return json.loads(self.cache_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def write_cache(self, cache: dict) -> None:
        self.out.mkdir(parents=True, exist_ok=True)
        self.cache_file.write_text(json.dumps(cache, indent=1, sort_keys=True) + "\n", encoding="utf-8")

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


def is_archived(name: str) -> bool:
    """Targets in targets/archive/, such as applications already sent."""
    return name == "archive" or name.startswith("archive/")


def _version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "unknown"


def fingerprint(doc: dict, stem: str) -> str:
    """What decides a PDF: the RenderCV input, its file name, and the tool versions."""
    text = json.dumps([doc, stem, _version("prismcv"), _version("rendercv"), _version("rendercv-fonts")],
                      sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build(folder: Folder, cv: CV, name: str, only_lang: str | None, debug: bool,
          force: bool = False, cache: dict | None = None) -> list[str]:
    """Build one target and return any warnings.

    A PDF whose input has not changed since it was last built is kept, unless
    force or debug is set. cache maps "target|lang" to the fingerprint of the
    last build and is updated in place.
    """
    cache = {} if cache is None else cache
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
        key, stamp = f"{name}|{lang}", fingerprint(assembled.doc, stem)
        if not (force or debug) and cache.get(key) == stamp and pdf.is_file():
            pages = len(PdfReader(pdf).pages)
            print(f"  = {folder.rel(pdf)}  ({pages} page{'s' if pages != 1 else ''}, unchanged)")
            if limit and pages > limit:
                warnings.append(f"{name} ({lang}): {pages} pages, exceeds max_pages: {limit}")
            continue
        cache.pop(key, None)
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
        cache[key] = stamp

        pages = len(PdfReader(pdf).pages)
        print(f"  ✓ {folder.rel(pdf)}  ({pages} page{'s' if pages != 1 else ''})")
        if limit and pages > limit:
            warnings.append(f"{name} ({lang}): {pages} pages, exceeds max_pages: {limit}")
    return warnings
