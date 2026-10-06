"""Command-line interface: stock-screening <command> --year YYYY ..."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, config, review, scan, selection, sheets


def _year(value: str) -> str:
    if len(value) != 4 or not value.isdigit():
        raise argparse.ArgumentTypeError("year must be YYYY")
    return value


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stock-screening",
        description="Pre-screen a YYYY/YYYY-MM-DD photo archive for Adobe Stock candidates.")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--photos-root", type=Path, help="photo archive root (contains YYYY folders)")
    p.add_argument("--out-dir", type=Path, help="where results go (outside repo and archive)")
    p.add_argument("--config", type=Path, help="extra TOML file overriding config.toml")
    sub = p.add_subparsers(dest="command", required=True)

    def add(name: str, help_: str) -> argparse.ArgumentParser:
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("--year", type=_year, required=True)
        return sp

    sp = add("scan", "step 1a: analyze files of a year (cached, resumable)")
    sp.add_argument("--time-budget", type=float, default=0,
                    help="stop after N seconds with exit code 3; re-run to continue")
    sp.add_argument("--workers", type=int, default=0, help="worker processes (default: CPUs)")

    add("select", "step 1b: apply duplicate / technical / quality / burst rules")

    sp = add("sheets", "step 2a: render numbered contact sheets of passing files")
    sp.add_argument("--include-reviewed", action="store_true",
                    help="also include files that already have a review decision")

    sp = add("mark", "step 2b: record a decision for sheet IDs")
    sp.add_argument("--ids", required=True, help="e.g. '1-4,9,12'")
    sp.add_argument("--decision", required=True, choices=review.DECISIONS)
    sp.add_argument("--flags", default="", help=f"comma list of: {', '.join(review.FLAGS)}")
    sp.add_argument("--note", default="")

    add("status", "show progress for a year")

    sp = add("export", "write a list of files with a given decision")
    sp.add_argument("--decision", default="candidate", choices=review.DECISIONS)
    sp.add_argument("--path-prefix",
                    help="prepend this archive path (e.g. the macOS path Lightroom uses)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cfg = config.load(args.photos_root, args.out_dir, args.config)
    except config.ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        if args.command == "scan":
            return scan.run(cfg, args.year, args.time_budget, args.workers)
        if args.command == "select":
            return selection.run(cfg, args.year)
        if args.command == "sheets":
            return sheets.run(cfg, args.year, args.include_reviewed)
        if args.command == "mark":
            flags = [f.strip() for f in args.flags.split(",") if f.strip()]
            return review.mark(cfg, args.year, args.ids, args.decision, flags, args.note)
        if args.command == "status":
            return review.status(cfg, args.year)
        if args.command == "export":
            return review.export(cfg, args.year, args.decision, args.path_prefix)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
