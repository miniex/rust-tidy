#!/bin/sh
# Run the pytest suite.
set -eu

REPO_ROOT="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"

if ! command -v pytest >/dev/null 2>&1; then
    echo "pytest not found. Install with: pip install pytest" >&2
    exit 1
fi

cd "${REPO_ROOT}"
exec pytest "$@"
