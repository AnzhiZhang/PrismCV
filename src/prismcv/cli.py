"""The prismcv command."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import build as b
from .init import InitError, create


def run_build(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        folder = b.Folder(args.root)
        if not args.targets and not args.all:
            parser.print_help()
            archived = len(folder.targets(archived=True)) - len(folder.targets())
            print("\navailable targets:\n  " + "\n  ".join(folder.targets()))
            if archived:
                print(f"  (and {archived} archived)")
            return 1
        cv = folder.load()
        if args.lang and args.lang not in cv.languages:
            raise b.BuildError(f"unknown language '{args.lang}' (configured: {', '.join(cv.languages)})")
        names = folder.targets() if args.all else folder.select(args.targets)
    except b.BuildError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1

    cache = folder.read_cache()
    failed, warnings = [], []
    try:
        for name in names:
            print(name)
            try:
                warnings += b.build(folder, cv, name, args.lang, args.debug, args.force, cache)
            except b.BuildError as e:
                print(f"  ✗ {e}", file=sys.stderr)
                failed.append(name)
    finally:
        folder.write_cache(cache)
    for w in warnings:
        print(f"⚠ {w}")
    if failed:
        print(f"✗ failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


def run_init(args: argparse.Namespace) -> int:
    try:
        created = create(args.path, example=args.example)
    except InitError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    root = args.path.resolve()
    for path in created:
        print(f"  + {path.relative_to(root)}")
    print(f"Created a CV in {root}. Edit cv.yaml and content/, then run: prismcv build --all")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="prismcv", description="One source, every CV.")
    commands = ap.add_subparsers(dest="command", required=True)

    bp = commands.add_parser("build", help="build CV PDFs with RenderCV")
    bp.add_argument("targets", nargs="*", help="targets, folders of targets or globs, e.g. industry or 'applications/2026-10*'")
    bp.add_argument("--all", action="store_true", help="build every target except those in targets/archive/")
    bp.add_argument("--force", action="store_true", help="rebuild PDFs even if nothing they depend on has changed")
    bp.add_argument("--lang", help="only build this language")
    bp.add_argument("--debug", action="store_true", help="keep the generated RenderCV input next to the PDF")
    bp.add_argument("--root", type=Path, default=Path.cwd(), help="CV folder to build (default: current folder)")

    ip = commands.add_parser("init", help="create a new CV folder")
    ip.add_argument("path", nargs="?", type=Path, default=Path.cwd(), help="folder to create it in (default: current folder)")
    ip.add_argument("--example", action="store_true", help="start from the full bilingual example instead of the minimal template")

    args = ap.parse_args()
    if args.command == "init":
        return run_init(args)
    return run_build(args, bp)


if __name__ == "__main__":
    sys.exit(main())
