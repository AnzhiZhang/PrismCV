"""Read and write the portable PrismCV repository format."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

import yaml

from .core import CV, PrismError, explain, target_languages


class FilesError(ValueError):
    """The supplied file mapping is not a valid PrismCV repository."""


@dataclass
class Entry:
    """One content entry and the extension-free file that owns it."""

    id: str
    file: str
    fields: dict[str, Any] | list[Any]


@dataclass
class Target:
    """One target, named relative to targets/ and without its extension."""

    name: str
    data: dict[str, Any]


@dataclass
class CVData:
    """A lossless, file-shaped PrismCV repository."""

    header: dict[str, Any]
    section_titles: dict[str, Any]
    languages: dict[str, str]
    design: dict[str, Any]
    entries: list[Entry]
    targets: list[Target]


def _path(raw: str) -> str:
    path = PurePosixPath(raw.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        raise FilesError(f"unsafe path: {raw}")
    return str(path)


def _clean_paths(files: Mapping[str, str]) -> dict[str, str]:
    clean: dict[str, str] = {}
    for raw, text in files.items():
        name = _path(raw)
        if name in clean:
            raise FilesError(f"duplicate path after normalisation: {name}")
        clean[name] = text
    return clean


def _yaml(files: Mapping[str, str], name: str) -> Any:
    try:
        value = yaml.safe_load(files[name])
    except KeyError:
        raise FilesError(f"missing {name}") from None
    except yaml.YAMLError as exc:
        raise FilesError(f"{name}: invalid YAML: {exc}") from None
    return value or {}


def read_files(files: Mapping[str, str], *, check: bool = True) -> CVData:
    """Parse a repository, optionally assembling every target and language."""
    clean = _clean_paths(files)
    cv_doc, design_doc = _yaml(clean, "cv.yaml"), _yaml(clean, "design.yaml")
    if not isinstance(cv_doc, dict) or not isinstance(design_doc, dict):
        raise FilesError("cv.yaml and design.yaml must contain mappings")
    languages = design_doc.get("languages")
    if not isinstance(languages, dict) or not languages:
        raise FilesError("design.yaml: languages must be a non-empty mapping")
    if not all(
        isinstance(code, str) and isinstance(locale, str)
        for code, locale in languages.items()
    ):
        raise FilesError("design.yaml: languages must map codes to RenderCV locales")

    entries: list[Entry] = []
    locations: dict[str, str] = {}
    for name in sorted(clean):
        path = PurePosixPath(name)
        if len(path.parts) < 2 or path.parts[0] != "content" or path.suffix != ".yaml":
            continue
        document = _yaml(clean, name)
        if not isinstance(document, dict):
            raise FilesError(f"{name}: top level must map ids to entries")
        file = str(path.relative_to("content").with_suffix(""))
        for entry_id, fields in document.items():
            if not isinstance(entry_id, str):
                raise FilesError(f"{name}: entry ids must be text")
            if entry_id in locations:
                raise FilesError(
                    f"duplicate id '{entry_id}' in {locations[entry_id]} and {name}"
                )
            if not isinstance(fields, (dict, list)):
                raise FilesError(f"{name}: {entry_id} must be a mapping or list")
            locations[entry_id] = name
            entries.append(Entry(entry_id, file, copy.deepcopy(fields)))

    targets: list[Target] = []
    for name in sorted(clean):
        path = PurePosixPath(name)
        if len(path.parts) < 2 or path.parts[0] != "targets" or path.suffix != ".yaml":
            continue
        document = _yaml(clean, name)
        if not isinstance(document, dict):
            raise FilesError(f"{name}: top level must be a mapping")
        targets.append(
            Target(
                str(path.relative_to("targets").with_suffix("")),
                copy.deepcopy(document),
            )
        )

    data = CVData(
        header=copy.deepcopy(cv_doc.get("header", {})),
        section_titles=copy.deepcopy(cv_doc.get("sections", {})),
        languages=copy.deepcopy(languages),
        design={
            key: copy.deepcopy(value)
            for key, value in design_doc.items()
            if key != "languages"
        },
        entries=entries,
        targets=targets,
    )
    try:
        cv = CV.from_data(data)
    except PrismError as exc:
        raise FilesError(explain(exc, _entry_files(data))) from None
    if check:
        entry_files = _entry_files(data)
        for target in targets:
            try:
                langs = target_languages(target.data, cv)
                cv.file_stems(target.data, target.name, langs)
                for lang in langs:
                    cv.assemble(target.data, lang)
            except PrismError as exc:
                raise FilesError(explain(exc, entry_files, target.name)) from None
    return data


def write_files(data: CVData) -> dict[str, str]:
    """Write typed PrismCV data to deterministic, readable YAML files."""
    rest = copy.deepcopy(data.design)
    design = {"file_name": rest.pop("file_name")} if "file_name" in rest else {}
    design["languages"] = _BlockMap(copy.deepcopy(data.languages))
    design.update(rest)
    result = {
        "cv.yaml": _dump(
            {
                "header": copy.deepcopy(data.header),
                "sections": copy.deepcopy(data.section_titles),
            },
            data.languages,
        ),
        "design.yaml": _dump(design, data.languages),
    }
    grouped: dict[str, dict[str, Any]] = {}
    for entry in data.entries:
        grouped.setdefault(_relative_name(entry.file), {})[entry.id] = copy.deepcopy(
            entry.fields
        )
    for file, entries in sorted(grouped.items()):
        result[f"content/{file}.yaml"] = _dump(entries, data.languages)
    for target in sorted(data.targets, key=lambda item: item.name):
        name = _relative_name(target.name)
        result[f"targets/{name}.yaml"] = _dump(target.data, data.languages)
    return result


def _relative_name(raw: str) -> str:
    name = _path(raw)
    path = PurePosixPath(name)
    if name in {"", "."} or path.suffix:
        raise FilesError(f"expected a relative name without an extension: {raw}")
    return name


def _entry_files(data: CVData) -> dict[str, str]:
    return {entry.id: f"content/{entry.file}.yaml" for entry in data.entries}


class _FlowMap(dict):
    pass


class _BlockMap(dict):
    pass


class _Dumper(yaml.SafeDumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, indentless=False)

    def write_indicator(self, indicator, need_whitespace, whitespace=False, indention=False):
        if indicator == "}":
            self.stream.write(" ")
            self.column += 1
            self.whitespace = True
        super().write_indicator(indicator, need_whitespace, whitespace, indention)
        if indicator == "{":
            self.stream.write(" ")
            self.column += 1
            self.whitespace = True


def _represent_flow_map(dumper: _Dumper, value: _FlowMap):
    return dumper.represent_mapping(
        "tag:yaml.org,2002:map", value.items(), flow_style=True
    )


_Dumper.add_representer(_FlowMap, _represent_flow_map)


def _represent_string(dumper: _Dumper, value: str):
    style = '"' if "," in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_Dumper.add_representer(str, _represent_string)


def _readable(value: Any, languages: Mapping[str, str], *, in_sequence: bool = False) -> Any:
    if isinstance(value, dict):
        keys = set(value)
        localized = (
            not isinstance(value, _BlockMap) and bool(keys) and keys <= set(languages)
        )
        items = (
            ((code, value[code]) for code in languages if code in value)
            if localized
            else value.items()
        )
        result = {key: _readable(item, languages) for key, item in items}
        if localized and not in_sequence and all(
            isinstance(item, str) and "\n" not in item for item in result.values()
        ):
            length = (
                sum(len(str(key)) + len(item) + 4 for key, item in result.items()) + 2
            )
            if length <= 88:
                return _FlowMap(result)
        return result
    if isinstance(value, list):
        return [_readable(item, languages, in_sequence=True) for item in value]
    return value


def _dump(value: Any, languages: Mapping[str, str]) -> str:
    chunks = []
    for key, item in value.items():
        chunk = yaml.dump(
            {key: _readable(item, languages)},
            Dumper=_Dumper,
            allow_unicode=True,
            sort_keys=False,
            width=100,
        ).rstrip()
        chunks.append(chunk)
    return "\n\n".join(chunks) + "\n"


__all__ = ["CVData", "Entry", "FilesError", "Target", "read_files", "write_files"]
