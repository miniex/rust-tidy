#!/bin/sh
# Auto-format Python and shell sources in this repo.
set -eu

REPO_ROOT="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"

if ! command -v ruff >/dev/null 2>&1; then
    echo "ruff not found. Install with: pip install ruff" >&2
    exit 1
fi

ruff format "${REPO_ROOT}"
ruff check --fix "${REPO_ROOT}"

if command -v shfmt >/dev/null 2>&1; then
    find "${REPO_ROOT}/tools" -type f -name '*.sh' -exec shfmt -ln posix -i 4 -ci -w {} +
else
    echo "warning: shfmt not found, skipping shell formatting" >&2
fi
