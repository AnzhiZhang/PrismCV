#!/usr/bin/env python3
"""Assemble RenderCV input files from content/ + targets/, then render PDFs.

Usage:
    python build.py industry                 # one target (both langs it lists)
    python build.py jobs/2026-10-15_acme     # a job target
    python build.py --all                    # every target
    python build.py industry --lang en       # only one language
    python build.py industry --debug         # also keep the assembled YAML and Typst files
"""

from __future__ import annotations

import argparse
import copy
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

LANGS = ("en", "zh")
SPECIAL_FILES = {"header.yaml", "sections.yaml"}
SCHEMA = "https://raw.githubusercontent.com/rendercv/rendercv/refs/tags/v2.8/schema.json"

# Field names RenderCV entries can have. A one-key mapping in a target whose key
# is not an id and not one of these is almost certainly a mistyped id.
ENTRY_FIELDS = {
    "text", "bullet", "label", "details", "number", "reversed_number",
    "company", "position", "institution", "area", "degree", "name",
    "title", "authors", "journal", "doi", "url", "summary", "highlights",
    "date", "start_date", "end_date", "location",
}

OMIT = object()  # a value explicitly set to null for one language


class BuildError(Exception):
    pass


# ---------------------------------------------------------------- loading

def load_yaml(path: Path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_pool() -> tuple[dict, dict]:
    """Merge every content/*.yaml (except header/sections) into one id -> entry pool."""
    pool, where = {}, {}
    for path in sorted(CONTENT.rglob("*.yaml")):
        if path.name in SPECIAL_FILES:
            continue
        data = load_yaml(path) or {}
        if not isinstance(data, dict):
            raise BuildError(f"{rel(path)}: top level must be a mapping of id -> entry")
        for eid, entry in data.items():
            if eid in pool:
                raise BuildError(f"duplicate id '{eid}' in {rel(where[eid])} and {rel(path)}")
            pool[eid], where[eid] = entry, path
    return pool, where


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


# ---------------------------------------------------------------- languages

def is_localized(value) -> bool:
    return isinstance(value, dict) and bool(value) and set(value) <= set(LANGS)


def localize(value, lang: str, where: str):
    """Resolve every {en: ..., zh: ...} in value to the given language."""
    if is_localized(value):
        if lang not in value:
            raise BuildError(f"{where}: missing '{lang}' text")
        if value[lang] is None:
            return OMIT
        return localize(value[lang], lang, where)
    if isinstance(value, dict):
        if set(value) & set(LANGS):
            extra = sorted(set(value) - set(LANGS))
            raise BuildError(f"{where}: unexpected keys {extra} next to en/zh "
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


# ---------------------------------------------------------------- entries

def resolve_id(eid: str, pool: dict, stack: tuple = ()):
    """Return a fresh copy of an entry, with its base (variant parent) applied."""
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


def resolve_item(item, pool: dict, where: str) -> list:
    """A target list item -> list of entries (an id may hold a list, e.g. a skills group)."""
    if isinstance(item, str):
        entry = resolve_id(item, pool)
    elif isinstance(item, dict) and len(item) == 1 and next(iter(item)) in pool:
        eid, override = next(iter(item.items()))
        entry = resolve_id(eid, pool)
        if override:
            if not isinstance(entry, dict):
                raise BuildError(f"{where}: '{eid}' cannot be overridden field by field")
            entry.update(copy.deepcopy(override))
    elif isinstance(item, dict):
        if len(item) == 1 and next(iter(item)) not in ENTRY_FIELDS:
            raise BuildError(f"{where}: unknown id '{next(iter(item))}'")
        entry = copy.deepcopy(item)  # an inline entry written directly in the target
    else:
        raise BuildError(f"{where}: cannot understand item {item!r}")
    entries = entry if isinstance(entry, list) else [entry]
    return [simplify(e) for e in entries]


def simplify(entry):
    """{text: ...} on its own is a plain text entry (e.g. a profile paragraph)."""
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


# ---------------------------------------------------------------- assembling

def assemble(target_name: str, target: dict, lang: str, pool: dict) -> dict:
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
                resolved = resolve_item(item, pool, f"{where}[{i}]")
            except BuildError as e:
                msg = str(e)
                raise BuildError(msg if msg.startswith("targets/") else f"{where}[{i}]: {msg}") from None
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
    doc.update(localize(load_yaml(DESIGN) or {}, lang, "design.yaml"))
    return doc


def output_names(target_name: str, lang: str, english_name: str) -> tuple[Path, str]:
    folder = OUT / target_name
    stem = re.sub(r"\W+", "_", english_name).strip("_") or "CV"
    return folder, f"{stem}_CV_{lang}"


def write_input(doc: dict, folder: Path, stem: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    settings = doc.setdefault("settings", {})
    rc = settings.setdefault("render_command", {})
    rc.update({
        "output_folder": ".",
        "pdf_path": f"{stem}.pdf",
        "typst_path": f"{stem}.typ",  # needed: the PDF is compiled from it
        "dont_generate_markdown": True,
        "dont_generate_html": True,
        "dont_generate_png": True,
    })
    path = folder / f"{stem}.yaml"
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# yaml-language-server: $schema={SCHEMA}\n")
        f.write("# Generated by build.py - edit content/ and targets/, not this file.\n")
        yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False, width=1000)
    return path


def render(yaml_path: Path) -> None:
    exe = shutil.which("rendercv", path=str(Path(sys.executable).parent)) or shutil.which("rendercv")
    if not exe:
        raise BuildError("rendercv not found - activate the conda env first: conda activate rendercv")
    proc = subprocess.run([exe, "render", yaml_path.name], cwd=yaml_path.parent,
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise BuildError(f"RenderCV failed (run again with --debug to keep the input YAML):\n{proc.stdout}{proc.stderr}")


# ---------------------------------------------------------------- CLI

def all_targets() -> list[str]:
    return sorted(str(p.relative_to(TARGETS).with_suffix("")) for p in TARGETS.rglob("*.yaml"))


def normalise(name: str) -> str:
    name = name.removeprefix("targets/").removesuffix(".yaml")
    if not (TARGETS / f"{name}.yaml").exists():
        raise BuildError(f"no such target: targets/{name}.yaml")
    return name


def build(name: str, pool: dict, only_lang: str | None, debug: bool) -> list[str]:
    target = load_yaml(TARGETS / f"{name}.yaml") or {}
    langs = target.get("langs") or list(LANGS)
    limit = target.get("max_pages")
    if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit < 1):
        raise BuildError(f"targets/{name}.yaml: max_pages must be a positive whole number (or left out for no limit)")
    if only_lang:
        langs = [l for l in langs if l == only_lang]
    english_name = localize((load_yaml(CONTENT / "header.yaml") or {}).get("name", "CV"), "en", "header.name")
    warnings = []
    for lang in langs:
        if lang not in LANGS:
            raise BuildError(f"targets/{name}.yaml: unknown language '{lang}'")
        doc = assemble(name, target, lang, pool)
        out_folder, stem = output_names(name, lang, english_name)
        out_folder.mkdir(parents=True, exist_ok=True)
        pdf = out_folder / f"{stem}.pdf"
        with tempfile.TemporaryDirectory(prefix="cv-") as tmp:
            work = Path(tmp)
            path = write_input(doc, work, stem)
            try:
                render(path)
            finally:
                if debug:  # keep the intermediate files next to the PDF
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
    ap = argparse.ArgumentParser(description="Build CV PDFs from content/ and targets/.")
    ap.add_argument("targets", nargs="*", help="target names, e.g. industry or jobs/2026-10-15_acme")
    ap.add_argument("--all", action="store_true", help="build every target")
    ap.add_argument("--lang", choices=LANGS, help="only build this language")
    ap.add_argument("--debug", action="store_true", help="also keep the assembled YAML and Typst files in out/")
    args = ap.parse_args()

    if not args.targets and not args.all:
        ap.print_help()
        print("\navailable targets:\n  " + "\n  ".join(all_targets()))
        return 1

    try:
        pool, _ = load_pool()
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
