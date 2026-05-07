# Contributing

Thanks for sending changes. The bar is small but firm: every commit and PR must pass `tools/format.sh`, `tools/lint.sh`, and `tools/test.sh` cleanly.

## Required tools

Install on your `$PATH` before working on this repo:

- [`ruff`](https://github.com/astral-sh/ruff) — Python formatter + linter
- [`pytest`](https://docs.pytest.org/) — Python test runner
- [`shfmt`](https://github.com/mvdan/sh) — shell script formatter
- [`shellcheck`](https://www.shellcheck.net/) — shell script linter

Examples:

```bash
# macOS
brew install ruff shfmt shellcheck
pip install pytest

# Arch
sudo pacman -S ruff shfmt shellcheck python-pytest

# pip-only (any OS)
pip install ruff pytest

# Linux: prefer your distro package, otherwise grab a release tarball.
```

For a full development install (CLI + dev deps):

```bash
pip install -e '.[dev]'
```

## Workflow

Before every commit:

```bash
./tools/format.sh   # rewrites Python via ruff + shell scripts via shfmt
./tools/lint.sh     # ruff format --check + ruff check + shellcheck + shfmt -d
./tools/test.sh     # pytest
```

Each script exits non-zero on any drift, lint finding, or test failure. CI / reviewers expect a clean run.

Smoke-test the CLI end-to-end after touching parser/CLI logic:

```bash
rust-tidy lint --fix path/to/some/rust/repo
rust-tidy sort --check path/to/some/rust/repo
```

## PR expectations

- Keep changes scoped — one concern per PR.
- Update `README.md` when behavior, flags, or required tools change.
- Match the existing layout: package code in `src/rust_tidy/`, tests in `tests/`, dev shell scripts in `tools/`.
- Shell scripts in `tools/` must remain POSIX (`#!/bin/sh`, `set -eu`, no bashisms) and pass `shellcheck` with `shell=sh`.
- New lint rules / sort behavior must come with fixture-based tests in `tests/test_lint_imports.py` or `tests/test_sort_toml.py`.
- `--fix` and `sort` rewrites must be **idempotent** — running them twice should be a no-op. Add an explicit test if you change the output shape.
- Keep `lint_imports.py` and `sort_toml.py` free of third-party deps; the only runtime requirement is the Python stdlib.

## Commit messages

Follow the prefixes already in `git log`. Shape: `prefix(scope?): description`.

Common prefixes: `feat`, `fix`, `refactor`, `perf`, `docs`, `chore`, `tools`, `tests`.

Rules:

- **Prefix is always lowercase** — `feat:` not `Feat:`.
- **First word after the prefix is always lowercase** — `fix: handle inline mod`, not `fix: Handle inline mod`.
- The rest of the description follows no strict case rule, but prefer lowercase. Reserve uppercase for proper nouns, acronyms, or genuine emphasis.

Examples:

```
feat: add --fix flag to lint subcommand
feat(sort): canonicalize inline-table key order
fix(lint): exempt inline mod from after-code rule
refactor: split parser into ScopeResult / Segment
docs: add CLI examples to README
tests: cover orphan-comment fix-blocker path
```

Single-line, imperative mood. No trailing period.
