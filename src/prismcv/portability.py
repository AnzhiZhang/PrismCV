"""Read and write the portable PrismCV repository format."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any

import yaml

from .core import CV, PrismError, target_languages


class FilesError(ValueError):
    """The supplied file mapping is not a valid PrismCV repository."""


def _path(raw: str) -> str:
    path = PurePosixPath(raw.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        raise FilesError(f"unsafe path: {raw}")
    return str(path)


def _yaml(files: Mapping[str, str], name: str) -> Any:
    try:
        value = yaml.safe_load(files[name])
    except KeyError:
        raise FilesError(f"missing {name}") from None
    except yaml.YAMLError as exc:
        raise FilesError(f"{name}: invalid YAML: {exc}") from None
    return value or {}


def read_files(files: Mapping[str, str]) -> dict[str, Any]:
    """Parse an in-memory CV folder into lossless, platform-friendly data."""
    clean = {_path(name): text for name, text in files.items()}
    cv_doc, design_doc = _yaml(clean, "cv.yaml"), _yaml(clean, "design.yaml")
    if not isinstance(cv_doc, dict) or not isinstance(design_doc, dict):
        raise FilesError("cv.yaml and design.yaml must contain mappings")
    languages = design_doc.get("languages")
    if not isinstance(languages, dict) or not languages:
        raise FilesError("design.yaml: languages must be a non-empty mapping")

    entries: list[dict[str, Any]] = []
    by_key: dict[str, Any] = {}
    for name in sorted(clean):
        path = PurePosixPath(name)
        if len(path.parts) != 2 or path.parts[0] != "content" or path.suffix != ".yaml":
            continue
        document = _yaml(clean, name)
        if not isinstance(document, dict):
            raise FilesError(f"{name}: top level must map ids to entries")
        for key, fields in document.items():
            if not isinstance(key, str) or key in by_key:
                raise FilesError(f"duplicate or invalid entry id: {key}")
            if not isinstance(fields, (dict, list)):
                raise FilesError(f"{name}: {key} must be a mapping or list")
            by_key[key] = fields
            entries.append(
                {
                    "key": key,
                    "group": path.stem,
                    "parent": key.split("@", 1)[0] if "@" in key else None,
                    "fields": copy.deepcopy(fields),
                }
            )

    targets: list[dict[str, Any]] = []
    for name in sorted(clean):
        path = PurePosixPath(name)
        if len(path.parts) < 2 or path.parts[0] != "targets" or path.suffix != ".yaml":
            continue
        document = _yaml(clean, name)
        if not isinstance(document, dict):
            raise FilesError(f"{name}: top level must be a mapping")
        targets.append(
            {"name": str(path.relative_to("targets").with_suffix("")), "data": document}
        )

    try:
        cv = CV(cv_doc, design_doc, by_key)
        for target in targets:
            langs = target_languages(target["data"], cv)
            cv.file_stems(target["data"], target["name"], langs)
            for lang in langs:
                cv.assemble(target["data"], lang)
    except PrismError as exc:
        raise FilesError(str(exc)) from None

    return {
        "header": copy.deepcopy(cv_doc.get("header", {})),
        "section_titles": copy.deepcopy(cv_doc.get("sections", {})),
        "languages": [
            {"code": code, "locale": locale} for code, locale in languages.items()
        ],
        "design": {
            key: copy.deepcopy(value)
            for key, value in design_doc.items()
            if key != "languages"
        },
        "entries": entries,
        "targets": targets,
    }


def write_files(data: Mapping[str, Any]) -> dict[str, str]:
    """Write parsed/platform data to deterministic, readable YAML files."""
    languages = data.get("languages", [])
    rest = copy.deepcopy(data.get("design", {}))
    design = {"file_name": rest.pop("file_name")} if "file_name" in rest else {}
    design["languages"] = {item["code"]: item["locale"] for item in languages}
    design.update(rest)
    result = {
        "cv.yaml": _dump(
            {
                "header": data.get("header", {}),
                "sections": data.get("section_titles", {}),
            }
        ),
        "design.yaml": _dump(design),
    }
    grouped: dict[str, dict[str, Any]] = {}
    for entry in data.get("entries", []):
        grouped.setdefault(entry["group"], {})[entry["key"]] = copy.deepcopy(
            entry["fields"]
        )
    for group, entries in sorted(grouped.items()):
        result[f"content/{group}.yaml"] = _dump(entries)
    for target in sorted(data.get("targets", []), key=lambda item: item["name"]):
        name = _path(target["name"])
        result[f"targets/{name}.yaml"] = _dump(target["data"])
    return result


def _dump(value: Any) -> str:
    return yaml.safe_dump(value, allow_unicode=True, sort_keys=False, width=1000)


__all__ = ["FilesError", "read_files", "write_files"]
