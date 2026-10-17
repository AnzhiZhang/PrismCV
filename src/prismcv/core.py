"""Turn CV data into RenderCV input.

Everything here works on plain dictionaries, the same data a CV folder holds:
cv.yaml (header and section titles), design.yaml, the entries in content/,
and one target. Nothing reads files or keeps global state, so the command
line and other programs can share it.

While assembling, every value in the result is mapped back to where it was
written (a Source), so problems can be reported against the user's own data.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any

# Fields a RenderCV entry can have. A one-key item in a target whose key is
# neither an id nor one of these is reported as an unknown id.
ENTRY_FIELDS = {
    "text", "bullet", "label", "details", "number", "reversed_number",
    "company", "position", "institution", "area", "degree", "name",
    "title", "authors", "journal", "doi", "url", "summary", "highlights",
    "date", "start_date", "end_date", "location",
}

# Fields that are not prose and are never changed by literal-text handling.
NOT_PROSE = {
    "url", "doi", "email", "phone", "website", "photo", "social_networks",
    "date", "start_date", "end_date",
}

# Marks text explicitly set to null for one language, so it is left out.
OMIT = object()

Key = tuple[str, ...]


# Reporting

@dataclass(frozen=True)
class Source:
    """Where a value was written.

    kind is one of:
      "header"  the header in cv.yaml; path is inside it
      "title"   a section title in cv.yaml; key is the section key
      "design"  design.yaml; key is a language code for that language's block, else None
      "entry"   an entry; key is its id, path is inside the entry
      "target"  the target; key is a section key and path starts with the item's
                index, or key is None and path starts with "header"
    """

    kind: str
    key: str | None = None
    path: tuple = ()

    def child(self, *parts) -> Source:
        return Source(self.kind, self.key, self.path + parts)


@dataclass
class Issue:
    """One problem, with where it was written and where it is in the RenderCV input."""

    message: str
    source: Source | None = None
    location: Key = ()


class PrismError(Exception):
    """One or more problems that stop a CV from being assembled or rendered."""

    def __init__(self, issues: list[Issue] | Issue):
        self.issues = issues if isinstance(issues, list) else [issues]
        super().__init__("; ".join(i.message for i in self.issues))


def fail(message: str, source: Source | None = None):
    raise PrismError(Issue(message, source))


def key(*parts) -> Key:
    return tuple(str(p) for p in parts)


# The data

@dataclass
class Assembled:
    """RenderCV input for one target in one language, with the source of every value."""

    doc: dict
    sources: dict[Key, Source] = field(default_factory=dict)

    def source_of(self, location) -> Source | None:
        """The source of a location in doc, or of the nearest enclosing value that has one."""
        loc = key(*location)
        while loc:
            if loc in self.sources:
                found = self.sources[loc]
                return found
            loc = loc[:-1]
        return None


class CV:
    """A whole CV: header and section titles, design, and the entries by id."""

    def __init__(self, cv: dict | None, design: dict | None, entries: dict | None):
        cv = cv or {}
        if not isinstance(cv, dict):
            fail("top level must be a mapping with header and sections", Source("header"))
        self.header = dict(cv.get("header") or {})
        self.titles = dict(cv.get("sections") or {})

        design = dict(design or {})
        langs = design.pop("languages", None) or {"en": "english"}
        if not isinstance(langs, dict) or not all(isinstance(v, str) for v in langs.values()):
            fail("languages must map language codes to RenderCV locales, e.g. en: english",
                 Source("design", None, ("languages",)))
        self.locales: dict[str, str] = dict(langs)
        self.file_name = design.pop("file_name", None)
        if self.file_name is not None:
            check_file_name(self.file_name, Source("design", None, ("file_name",)))
        self.lang_design = {c: design.pop(c) or {} for c in list(langs) if c in design}
        self.design = design
        self.entries = entries or {}

    @property
    def languages(self) -> tuple[str, ...]:
        return tuple(self.locales)

    # Languages

    def is_localized(self, value) -> bool:
        return isinstance(value, dict) and bool(value) and set(value) <= set(self.locales)

    def localize(self, value, lang: str, src: Source | None = None,
                 out: Key | None = None, sources: dict | None = None,
                 list_sources: list[Source] | None = None):
        """Replace every {en: ..., zh: ...} mapping inside value with the text for lang.

        A language set to null gives OMIT, which is left out of the enclosing
        mapping or list. When sources is given, the source of every value is
        recorded under its location (out) in the result.
        """
        if self.is_localized(value):
            if lang not in value:
                fail(f"missing '{lang}' text", src)
            if value[lang] is None:
                return OMIT
            return self.localize(value[lang], lang, src and src.child(lang), out, sources)
        if sources is not None and out is not None and src is not None:
            sources[out] = src
        if isinstance(value, dict):
            if set(value) & set(self.locales):
                extra = sorted(set(value) - set(self.locales))
                fail(f"unexpected keys {extra} next to language keys "
                     "- put text containing commas in quotes, e.g. en: \"London, UK\"", src)
            result = {}
            for k, v in value.items():
                v = self.localize(v, lang, src and src.child(k), out and out + key(k), sources)
                if v is not OMIT:
                    result[k] = v
            return result
        if isinstance(value, list):
            result = []
            for i, v in enumerate(value):
                item_src = list_sources[i] if list_sources is not None else src and src.child(i)
                v = self.localize(v, lang, item_src, out and out + key(len(result)), sources)
                if v is not OMIT:
                    result.append(v)
            return result
        return value

    # Design

    def design_for(self, lang: str) -> tuple[dict, dict[Key, Source]]:
        """RenderCV design, locale and settings for one language, and their sources."""
        doc = copy.deepcopy(self.design)
        merge(doc.setdefault("design", {}), copy.deepcopy(self.lang_design.get(lang, {})))
        if "theme" not in doc["design"]:
            # RenderCV's default theme; RenderCV 2.8 fails on a design without one.
            doc["design"] = {"theme": "classic", **doc["design"]}
        doc.setdefault("locale", {})["language"] = self.locales[lang]
        own = self.lang_design.get(lang, {})

        def source(loc: tuple) -> Source:
            if loc[:1] == ("design",) and has_path(own, loc[1:]):
                return Source("design", lang, loc[1:])
            if loc == ("locale", "language"):
                return Source("design", None, ("languages", lang))
            return Source("design", None, loc)

        sources: dict[Key, Source] = {}
        for loc in walk(doc):
            sources[key(*loc)] = source(loc)
        doc = self.localize(doc, lang)
        return doc, sources

    # Entries

    def resolve_id(self, eid: str, stack: tuple = ()) -> list[tuple[Any, dict, Source]]:
        """An entry with its base (for variants) applied, as (entry, field sources, entry source).

        An id holding a list of entries gives one tuple per entry.
        """
        if eid not in self.entries:
            fail(f"unknown id '{eid}'")
        if eid in stack:
            fail(f"circular base: {' -> '.join(stack + (eid,))}", Source("entry", eid))
        entry = copy.deepcopy(self.entries[eid])
        here = Source("entry", eid)
        if isinstance(entry, list):
            return [(e, fields_of(e, here.child(j)), here.child(j)) for j, e in enumerate(entry)]
        if not isinstance(entry, dict):
            return [(entry, {}, here)]
        base = entry.pop("base", None)
        if base is None and "@" in eid:
            base = eid.split("@", 1)[0]
        if base is None:
            return [(entry, fields_of(entry, here), here)]
        parent = self.resolve_id(base, stack + (eid,))
        if len(parent) != 1 or not isinstance(parent[0][0], dict):
            fail(f"base '{base}' is not a single entry", here)
        merged, sources, _ = parent[0]
        merged.update(entry)
        sources.update(fields_of(entry, here))
        return [(merged, sources, here)]

    def resolve_item(self, item, section: str, i: int) -> list[tuple[Any, dict, Source]]:
        """Turn one item of a target section into entries with their sources.

        An item is an id, an id with fields to override, or an entry written inline.
        """
        at = Source("target", section, (i,))
        try:
            if isinstance(item, str):
                return [self.prepare_highlights(r) for r in self.resolve_id(item)]
            if isinstance(item, dict) and len(item) == 1 and next(iter(item)) in self.entries:
                eid, override = next(iter(item.items()))
                resolved = self.resolve_id(eid)
                if override is not None and not isinstance(override, dict):
                    fail(f"overrides for '{eid}' must be a mapping", at.child(eid))
                override = copy.deepcopy(override or {})
                hide = override.pop("hide", [])
                hide_src = at.child(eid, "hide")
                if not isinstance(hide, list) or any(not isinstance(b, str) or not b for b in hide):
                    fail(f"hide for '{eid}' must be a list of non-empty bullet ids", hide_src)
                if hide and len(resolved) != 1:
                    fail(f"'{eid}' is a list and cannot hide bullets", hide_src)
                if override:
                    if len(resolved) != 1 or not isinstance(resolved[0][0], dict):
                        fail(f"'{eid}' is a list and cannot be overridden field by field")
                    entry, sources, here = resolved[0]
                    entry.update(override)
                    sources.update(fields_of(override, at.child(eid)))
                return [self.prepare_highlights(r, hide, hide_src) for r in resolved]
            if isinstance(item, dict):
                if len(item) == 1 and next(iter(item)) not in ENTRY_FIELDS:
                    fail(f"unknown id '{next(iter(item))}'")
                return [self.prepare_highlights((copy.deepcopy(item), fields_of(item, at), at))]
            fail(f"cannot understand item {item!r}")
        except PrismError as e:
            for issue in e.issues:
                issue.source = issue.source or at
            raise

    def prepare_highlights(self, resolved: tuple, hide=(), hide_src: Source | None = None) -> tuple:
        """Strip bullet metadata after overrides, keeping each bullet's original source.

        Field sources with ("highlights", index) keys describe the normalized list.
        Identified bullets use their id; legacy bullets keep their original index.
        """
        entry, fields, here = resolved
        if isinstance(entry, dict) and "hide" in entry:
            fail("hide belongs in a target item's override mapping", fields["hide"])
        bullets, ids = [], set()
        if isinstance(entry, dict) and isinstance(entry.get("highlights"), list):
            origin = fields["highlights"]
            for i, bullet in enumerate(entry["highlights"]):
                src, bid = origin.child(i), None
                if isinstance(bullet, dict):
                    if "id" in bullet:
                        bid = bullet["id"]
                        if not isinstance(bid, str) or not bid:
                            fail("bullet id must be a non-empty string", src.child("id"))
                        src = origin.child(bid)
                        if bid in ids:
                            fail(f"duplicate bullet id '{bid}' in entry '{here.key}'", src)
                        ids.add(bid)
                    value = {k: v for k, v in bullet.items() if k != "id"}
                    if set(value) == {"text"}:
                        bullet = value["text"]
                        src = src.child("text")
                    else:
                        bullet = value
                if not (isinstance(bullet, str) or
                        (self.is_localized(bullet) and
                         all(v is None or isinstance(v, str) for v in bullet.values()))):
                    fail("bullet must be text or a language mapping, optionally with id and text", src)
                bullets.append((bid, bullet, src))
            entry["highlights"] = []
            for bid, bullet, src in bullets:
                if bid is None or bid not in hide:
                    fields[("highlights", len(entry["highlights"]))] = src
                    entry["highlights"].append(bullet)
        for bid in hide:
            if bid not in ids:
                fail(f"unknown hidden bullet id '{bid}' in entry '{here.key}'", hide_src)
        return simplify((entry, fields, here))

    # Assembling

    def assemble(self, target: dict, lang: str, *, literal: bool = False) -> Assembled:
        """Build the complete RenderCV input for one target in one language.

        With literal, prose is adjusted so it appears in the PDF exactly as
        written, apart from the Markdown RenderCV supports (bold, italic, links).
        """
        if lang not in self.locales:
            fail(f"language '{lang}' is not listed in languages", Source("design", None, ("languages",)))
        result = Assembled({})
        record = result.sources

        header = {k: (v, Source("header", None, (k,))) for k, v in self.header.items()}
        for k, v in (target.get("header") or {}).items():
            header[k] = (v, Source("target", None, ("header", k)))
        cv = {}
        for k, (v, src) in header.items():
            v = self.localize(v, lang, src, key("cv", k), record)
            if v is not OMIT:
                cv[k] = text(v, k) if literal else v

        cv["sections"] = {}
        for name, spec in (target.get("sections") or {}).items():
            if isinstance(spec, dict):
                items, title = spec.get("entries") or [], spec.get("title")
                title_src = Source("target", name, ("title",))
            else:
                items, title, title_src = spec or [], None, None
            if not title:
                title, title_src = self.titles.get(name), Source("title", name)
            if title is None:
                fail(f"no title (add '{name}' to sections in cv.yaml)", Source("target", name))
            title = self.localize(title, lang, title_src)
            if literal:
                title = text(title, "title")

            entries, sources = [], {}
            for i, item in enumerate(items):
                for entry, fields, here in self.resolve_item(item, name, i):
                    at = key("cv", "sections", title, len(entries))
                    if isinstance(entry, dict) and not self.is_localized(entry):
                        if set(entry) & set(self.locales):
                            extra = sorted(set(entry) - set(self.locales))
                            fail(f"unexpected keys {extra} next to language keys", here)
                        sources[at] = here
                        value = {}
                        for k, v in entry.items():
                            src = fields.get(k, here.child(k))
                            list_sources = ([fields[(k, j)] for j in range(len(v))]
                                            if k == "highlights" and isinstance(v, list) else None)
                            v = self.localize(v, lang, src, at + key(k), sources, list_sources)
                            if v is not OMIT:
                                value[k] = text(v, k) if literal else v
                    else:
                        value = self.localize(entry, lang, fields.get("text", here), at, sources)
                        if value is not OMIT and literal:
                            value = text(value, "text")
                    if value is not OMIT:
                        entries.append(value)
            if not entries:
                continue
            kinds = {entry_kind(e) for e in entries}
            if len(kinds) > 1:
                fail(f"mixed entry types {sorted(kinds)} in one section", Source("target", name))
            cv["sections"][title] = entries
            record[key("cv", "sections", title)] = Source("target", name)
            record.update(sources)

        result.doc = {"cv": cv}
        design, design_sources = self.design_for(lang)
        result.doc.update(design)
        record.update(design_sources)
        return result

    def file_stem(self, lang: str, target: dict | None = None, target_name: str = "") -> str:
        """File name for a PDF, without .pdf.

        From file_name in the target, else file_name in design.yaml, with
        {lang} and {target} filled in; without either, from the name in the
        first language, e.g. Ann_Lee_CV_en.
        """
        template = (target or {}).get("file_name")
        if template is not None:
            check_file_name(template, Source("target", None, ("file_name",)))
        else:
            template = self.file_name
        if template is None:
            name = self.localize(self.header.get("name", "CV"), self.languages[0], Source("header", None, ("name",)))
            stem = re.sub(r"\W+", "_", str(name)).strip("_") or "CV"
            return f"{stem}_CV_{lang}"
        return template.replace("{lang}", lang).replace("{target}", target_name.replace("/", "-"))

    def file_stems(self, target: dict, target_name: str, langs: list[str]) -> dict[str, str]:
        """File names for each language of a target; two languages may not share one."""
        stems = {lang: self.file_stem(lang, target, target_name) for lang in langs}
        if len(set(stems.values())) < len(stems):
            where = ("target", None, ("file_name",)) if "file_name" in target else ("design", None, ("file_name",))
            fail("gives every language the same file name; add {lang}", Source(*where))
        return stems


# File names

FILE_NAME_FIELDS = {"lang", "target"}
UNSAFE_IN_FILE_NAMES = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def check_file_name(template, source: Source) -> None:
    """A file_name must be text using only {lang} and {target}, giving a valid file name."""
    if not isinstance(template, str) or not template.strip():
        fail("must be text, e.g. Ann_Lee_CV_{lang}", source)
    fields = set(re.findall(r"{([^{}]*)}", template))
    if fields - FILE_NAME_FIELDS:
        fail(f"can only use {{lang}} and {{target}}, not {', '.join('{%s}' % f for f in sorted(fields - FILE_NAME_FIELDS))}", source)
    rest = re.sub(r"{(lang|target)}", "", template)
    if "{" in rest or "}" in rest or UNSAFE_IN_FILE_NAMES.search(rest):
        fail('cannot contain braces outside {lang} and {target}, or any of \\ / : * ? " < > |', source)
    if template.lower().endswith(".pdf"):
        fail("is written without .pdf", source)


# Targets

def target_languages(target: dict, cv: CV) -> list[str]:
    """The languages a target is built in, checked against the CV's languages."""
    langs = target.get("langs") or list(cv.languages)
    for lang in langs:
        if lang not in cv.locales:
            fail(f"language '{lang}' is not listed in design.yaml", Source("target", None, ("langs",)))
    return list(langs)


def max_pages(target: dict) -> int | None:
    limit = target.get("max_pages")
    if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit < 1):
        fail("max_pages must be a positive whole number (or left out for no limit)",
             Source("target", None, ("max_pages",)))
    return limit


# Literal text

WORD_JOINER = "⁠"
LINK_TARGET = re.compile(r"(\]\([^)]*\))")


def literal(s: str) -> str:
    """Stop RenderCV from reading parts of plain text as Typst code or layout.

    RenderCV passes #command(...)[...] and $$math$$ through to Typst, reads
    <name> as raw HTML, and splits " - " inside a bullet into sub-bullets.
    An invisible word joiner (or a no-break space for " - ") breaks each of
    these patterns without changing how the text looks. Link targets in
    Markdown links are left alone.
    """
    parts = LINK_TARGET.split(s)
    for i in range(0, len(parts), 2):
        p = parts[i]
        p = re.sub(r"#(?=[A-Za-z])", "#" + WORD_JOINER, p)
        p = re.sub(r"<(?=[A-Za-z/!?])", "<" + WORD_JOINER, p)
        p = p.replace("$$", "$" + WORD_JOINER + "$")
        p = p.replace(" - ", " - ")
        p = re.sub(r"(?m)^!!!", "!" + WORD_JOINER + "!!", p)
        parts[i] = p
    return "".join(parts)


def text(value, field_name: str):
    """Apply literal() to every string in a prose field."""
    if field_name in NOT_PROSE:
        return value
    if isinstance(value, str):
        return literal(value)
    if isinstance(value, list):
        return [text(v, field_name) for v in value]
    if isinstance(value, dict):
        return {k: text(v, k) for k, v in value.items()}
    return value


# Helpers

def merge(base: dict, extra: dict) -> dict:
    """Merge extra into base, recursing into nested mappings."""
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            merge(base[k], v)
        else:
            base[k] = v
    return base


def has_path(tree, path: tuple) -> bool:
    for p in path:
        if not isinstance(tree, dict) or p not in tree:
            return False
        tree = tree[p]
    return True


def walk(tree, path: tuple = ()):
    """Every location in nested mappings and lists."""
    if path:
        yield path
    if isinstance(tree, dict):
        for k, v in tree.items():
            yield from walk(v, path + (k,))
    elif isinstance(tree, list):
        for i, v in enumerate(tree):
            yield from walk(v, path + (i,))


def fields_of(entry, src: Source) -> dict:
    return {k: src.child(k) for k in entry} if isinstance(entry, dict) else {}


def simplify(resolved: tuple) -> tuple:
    """An entry with only a text field becomes a plain paragraph."""
    entry, fields, here = resolved
    if isinstance(entry, dict) and set(entry) == {"text"}:
        return entry["text"], fields, here
    return resolved


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
