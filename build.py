#!/usr/bin/env python3
"""Build CV PDFs from content/ and targets/ with RenderCV.

    python build.py industry          build one target
    python build.py --all             build every target
    python build.py industry --lang en
    python build.py industry --debug  keep the generated RenderCV input next to the PDF
"""

from __future__ import annotations

import argparse
import copy
import functools
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "content"
TARGETS = ROOT / "targets"
OUT = ROOT / "out"
DESIGN = ROOT / "design.yaml"

SPECIAL_FILES = {"header.yaml", "sections.yaml"}
SCHEMA = "https://raw.githubusercontent.com/rendercv/rendercv/refs/tags/v2.8/schema.json"

# Fields a RenderCV entry can have. A one-key item in a target whose key is
# neither an id nor one of these is reported as an unknown id.
ENTRY_FIELDS = {
    "text", "bullet", "label", "details", "number", "reversed_number",
    "company", "position", "institution", "area", "degree", "name",
    "title", "authors", "journal", "doi", "url", "summary", "highlights",
    "date", "start_date", "end_date", "location",
}

# Marks text explicitly set to null for one language, so it is left out.
OMIT = object()


class BuildError(Exception):
    pass


def load_yaml(path: Path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


@functools.cache
def load_design() -> tuple[dict, dict, dict]:
    """Read design.yaml: languages, the shared settings, and per-language settings."""
    data = load_yaml(DESIGN) or {}
    langs = data.pop("languages", None) or {"en": "english"}
    if not isinstance(langs, dict) or not all(isinstance(v, str) for v in langs.values()):
        raise BuildError("design.yaml: languages must map language codes to RenderCV locales, e.g. en: english")
    per_lang = {code: data.pop(code) or {} for code in list(langs) if code in data}
    return langs, data, per_lang


def languages() -> tuple[str, ...]:
    return tuple(load_design()[0])


def merge(base: dict, extra: dict) -> dict:
    """Merge extra into base, recursing into nested mappings."""
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            merge(base[k], v)
        else:
            base[k] = v
    return base


def design_for(lang: str) -> dict:
    """RenderCV design, locale and settings for one language."""
    langs, shared, per_lang = load_design()
    doc = copy.deepcopy(shared)
    merge(doc.setdefault("design", {}), copy.deepcopy(per_lang.get(lang, {})))
    doc.setdefault("locale", {})["language"] = langs[lang]
    return localize(doc, lang, "design.yaml")


def load_pool() -> dict:
    """Merge every content file (except header and sections) into one id -> entry pool."""
    pool, where = {}, {}
    for path in sorted(CONTENT.rglob("*.yaml")):
        if path.name in SPECIAL_FILES:
            continue
        data = load_yaml(path) or {}
        if not isinstance(data, dict):
            raise BuildError(f"{rel(path)}: top level must map ids to entries")
        for eid, entry in data.items():
            if eid in pool:
                raise BuildError(f"duplicate id '{eid}' in {rel(where[eid])} and {rel(path)}")
            pool[eid], where[eid] = entry, path
    return pool


# Languages

def is_localized(value) -> bool:
    return isinstance(value, dict) and bool(value) and set(value) <= set(languages())


def localize(value, lang: str, where: str):
    """Replace every {en: ..., zh: ...} mapping inside value with the text for lang."""
    if is_localized(value):
        if lang not in value:
            raise BuildError(f"{where}: missing '{lang}' text")
        if value[lang] is None:
            return OMIT
        return localize(value[lang], lang, where)
    if isinstance(value, dict):
        if set(value) & set(languages()):
            extra = sorted(set(value) - set(languages()))
            raise BuildError(f"{where}: unexpected keys {extra} next to language keys "
                             "- put text containing commas in quotes, e.g. en: \"London, UK\"")
        out = {}
        for k, v in value.items():
            v = localize(v, lang, f"{where}.{k}")
            if v is not OMIT:
                out[k] = v
        return out
    if isinstance(value, list):
        out = []
        for i, v in enumerate(value):
            v = localize(v, lang, f"{where}[{i}]")
            if v is not OMIT:
                out.append(v)
        return out
    return value


# Entries

def resolve_id(eid: str, pool: dict, stack: tuple = ()):
    """Return a copy of an entry with its base entry (for variants) applied."""
    if eid not in pool:
        raise BuildError(f"unknown id '{eid}'")
    if eid in stack:
        raise BuildError(f"circular base: {' -> '.join(stack + (eid,))}")
    entry = copy.deepcopy(pool[eid])
    if not isinstance(entry, dict):
        return entry
    base = entry.pop("base", None)
    if base is None and "@" in eid:
        base = eid.split("@", 1)[0]
    if base is None:
        return entry
    parent = resolve_id(base, pool, stack + (eid,))
    if not isinstance(parent, dict):
        raise BuildError(f"'{eid}': base '{base}' is not a single entry")
    parent.update(entry)
    return parent


def resolve_item(item, pool: dict) -> list:
    """Turn one item of a target section into a list of entries.

    An item is an id, an id with fields to override, or an entry written inline.
    An id may stand for a list of entries, such as a group of skills.
    """
    if isinstance(item, str):
        entry = resolve_id(item, pool)
    elif isinstance(item, dict) and len(item) == 1 and next(iter(item)) in pool:
        eid, override = next(iter(item.items()))
        entry = resolve_id(eid, pool)
        if override:
            if not isinstance(entry, dict):
                raise BuildError(f"'{eid}' is a list and cannot be overridden field by field")
            entry.update(copy.deepcopy(override))
    elif isinstance(item, dict):
        if len(item) == 1 and next(iter(item)) not in ENTRY_FIELDS:
            raise BuildError(f"unknown id '{next(iter(item))}'")
        entry = copy.deepcopy(item)
    else:
        raise BuildError(f"cannot understand item {item!r}")
    entries = entry if isinstance(entry, list) else [entry]
    return [simplify(e) for e in entries]


def simplify(entry):
    """An entry with only a text field becomes a plain paragraph."""
    if isinstance(entry, dict) and set(entry) == {"text"}:
        return entry["text"]
    return entry


def entry_kind(entry) -> str:
    if isinstance(entry, str):
        return "text"
    keys = set(entry)
    for kind, marker in (
        ("experience", {"company", "position"}), ("education", {"institution"}),
        ("publication", {"authors"}), ("one-line", {"label"}), ("bullet", {"bullet"}),
        ("numbered", {"number"}), ("reversed-numbered", {"reversed_number"}),
        ("normal", {"name"}),
    ):
        if marker <= keys:
            return kind
    return "unknown"


# Assembling

def assemble(target_name: str, target: dict, lang: str, pool: dict) -> dict:
    """Build the complete RenderCV input for one target in one language."""
    header = load_yaml(CONTENT / "header.yaml") or {}
    header.update(target.get("header") or {})
    titles = load_yaml(CONTENT / "sections.yaml") or {}

    cv = localize(header, lang, "header")
    cv["sections"] = {}
    for key, spec in (target.get("sections") or {}).items():
        where = f"targets/{target_name}.yaml: {key}"
        if isinstance(spec, dict):
            items, title = spec.get("entries") or [], spec.get("title")
        else:
            items, title = spec or [], None
        title = title or titles.get(key)
        if title is None:
            raise BuildError(f"{where}: no title (add '{key}' to content/sections.yaml)")
        title = localize(title, lang, f"{where}.title")

        entries = []
        for i, item in enumerate(items):
            try:
                resolved = resolve_item(item, pool)
            except BuildError as e:
                raise BuildError(f"{where}[{i}]: {e}") from None
            for e in resolved:
                e = localize(e, lang, f"{where}[{i}]")
                if e is not OMIT:
                    entries.append(e)
        if not entries:
            continue
        kinds = {entry_kind(e) for e in entries}
        if len(kinds) > 1:
            raise BuildError(f"{where}: mixed entry types {sorted(kinds)} in one section")
        cv["sections"][title] = entries

    doc = {"cv": cv}
    doc.update(design_for(lang))
    return doc


def write_input(doc: dict, folder: Path, stem: str) -> Path:
    settings = doc.setdefault("settings", {})
    settings.setdefault("render_command", {}).update({
        "output_folder": ".",
        "pdf_path": f"{stem}.pdf",
        "typst_path": f"{stem}.typ",
        "dont_generate_markdown": True,
        "dont_generate_html": True,
        "dont_generate_png": True,
    })
    path = folder / f"{stem}.yaml"
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# yaml-language-server: $schema={SCHEMA}\n")
        f.write("# Generated by build.py. Edit content/ and targets/ instead.\n")
        yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False, width=1000)
    return path


def render(yaml_path: Path) -> None:
    exe = shutil.which("rendercv", path=str(Path(sys.executable).parent)) or shutil.which("rendercv")
    if not exe:
        raise BuildError("rendercv not found - install the requirements: pip install -r requirements.txt")
    proc = subprocess.run([exe, "render", yaml_path.name], cwd=yaml_path.parent,
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise BuildError(f"RenderCV failed (run with --debug to keep its input):\n{proc.stdout}{proc.stderr}")


# Command line

def all_targets() -> list[str]:
    return sorted(str(p.relative_to(TARGETS).with_suffix("")) for p in TARGETS.rglob("*.yaml"))


def normalise(name: str) -> str:
    name = name.removeprefix("targets/").removesuffix(".yaml")
    if not (TARGETS / f"{name}.yaml").exists():
        raise BuildError(f"no such target: targets/{name}.yaml")
    return name


def file_stem(lang: str) -> str:
    """File name for a PDF, from the name in the first configured language."""
    name = (load_yaml(CONTENT / "header.yaml") or {}).get("name", "CV")
    name = localize(name, languages()[0], "header.name")
    stem = re.sub(r"\W+", "_", str(name)).strip("_") or "CV"
    return f"{stem}_CV_{lang}"


def build(name: str, pool: dict, only_lang: str | None, debug: bool) -> list[str]:
    """Build one target and return any warnings."""
    target = load_yaml(TARGETS / f"{name}.yaml") or {}
    langs = target.get("langs") or list(languages())
    limit = target.get("max_pages")
    if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit < 1):
        raise BuildError(f"targets/{name}.yaml: max_pages must be a positive whole number (or left out for no limit)")
    if only_lang:
        langs = [l for l in langs if l == only_lang]
        if not langs:
            print(f"  - skipped: this target is not built in '{only_lang}'")

    warnings = []
    for lang in langs:
        if lang not in languages():
            raise BuildError(f"targets/{name}.yaml: language '{lang}' is not listed in design.yaml")
        doc = assemble(name, target, lang, pool)
        out_folder = OUT / name
        out_folder.mkdir(parents=True, exist_ok=True)
        stem = file_stem(lang)
        pdf = out_folder / f"{stem}.pdf"
        with tempfile.TemporaryDirectory(prefix="cv-") as tmp:
            work = Path(tmp)
            path = write_input(doc, work, stem)
            try:
                render(path)
            finally:
                if debug:
                    for suffix in (".yaml", ".typ"):
                        if (work / f"{stem}{suffix}").exists():
                            shutil.copy2(work / f"{stem}{suffix}", out_folder / f"{stem}{suffix}")
            shutil.copy2(work / f"{stem}.pdf", pdf)

        pages = len(PdfReader(pdf).pages)
        print(f"  ✓ {rel(pdf)}  ({pages} page{'s' if pages != 1 else ''})")
        if limit and pages > limit:
            warnings.append(f"{name} ({lang}): {pages} pages, exceeds max_pages: {limit}")
    return warnings


def main() -> int:
    ap = argparse.ArgumentParser(description="Build CV PDFs from content/ and targets/ with RenderCV.")
    ap.add_argument("targets", nargs="*", help="target names, e.g. industry or jobs/2026-10-15_acme")
    ap.add_argument("--all", action="store_true", help="build every target")
    ap.add_argument("--lang", help="only build this language")
    ap.add_argument("--debug", action="store_true", help="keep the generated RenderCV input next to the PDF")
    args = ap.parse_args()

    if not args.targets and not args.all:
        ap.print_help()
        print("\navailable targets:\n  " + "\n  ".join(all_targets()))
        return 1

    try:
        if args.lang and args.lang not in languages():
            raise BuildError(f"unknown language '{args.lang}' (configured: {', '.join(languages())})")
        pool = load_pool()
        names = all_targets() if args.all else [normalise(t) for t in args.targets]
    except BuildError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1

    failed, warnings = [], []
    for name in names:
        print(name)
        try:
            warnings += build(name, pool, args.lang, args.debug)
        except BuildError as e:
            print(f"  ✗ {e}", file=sys.stderr)
            failed.append(name)
    for w in warnings:
        print(f"⚠ {w}")
    if failed:
        print(f"✗ failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
