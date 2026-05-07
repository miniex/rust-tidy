"""rust-tidy unified CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rust_tidy import __version__
from rust_tidy.diag import Reporter, timed
from rust_tidy.lint_imports import DEFAULT_EXCLUDE_DIRS as LINT_EXCLUDE
from rust_tidy.lint_imports import run as run_lint
from rust_tidy.sort_toml import DEFAULT_EXCLUDE_DIRS as SORT_EXCLUDE
from rust_tidy.sort_toml import run as run_sort


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[Path()],
        help="Files or directories to process (default: current directory).",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="DIR",
        help="Directory name to skip; may be repeated.",
    )
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="Colorize output (default: auto, honors NO_COLOR).",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rust-tidy",
        description="Tidy Rust projects: sort Cargo.toml deps and lint use ordering.",
    )
    parser.add_argument("--version", action="version", version=f"rust-tidy {__version__}")

    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    p_lint = sub.add_parser(
        "lint",
        help="Lint module-level use/mod ordering in .rs files.",
    )
    _add_common(p_lint)
    p_lint.add_argument(
        "--fix",
        action="store_true",
        help="Auto-fix violations in place (sort + normalize blank lines).",
    )

    p_sort = sub.add_parser(
        "sort",
        help="Sort dependency entries in Cargo.toml files.",
    )
    _add_common(p_sort)
    p_sort.add_argument(
        "--check",
        action="store_true",
        help="Do not write changes; emit a diff and exit 1 if any file would change.",
    )
    p_sort.add_argument(
        "--no-diff",
        action="store_true",
        help="In --check mode, suppress the diff output (only emit the warning).",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    reporter = Reporter(stream=sys.stderr, color_mode=args.color)

    if args.command == "lint":
        exclude = LINT_EXCLUDE | frozenset(args.exclude)
        with timed(reporter):
            code = run_lint(args.paths, reporter, exclude=exclude, fix=args.fix)
        reporter.summary("rust-tidy lint")
        return code

    if args.command == "sort":
        exclude = SORT_EXCLUDE | frozenset(args.exclude)
        with timed(reporter):
            code = run_sort(
                args.paths,
                reporter,
                exclude=exclude,
                check=args.check,
                show_diff=not args.no_diff,
            )
        reporter.summary("rust-tidy sort")
        return code

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
