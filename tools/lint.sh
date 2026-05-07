#!/bin/sh
# Lint Python and shell sources without modifying them.
# Exits non-zero if any checker reports issues or is missing.
set -eu

REPO_ROOT="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"

status=0

run_check() {
    name=$1
    shift
    if ! "$@"; then
        echo "[FAIL] ${name}" >&2
        status=1
    fi
}

if command -v ruff >/dev/null 2>&1; then
    run_check "ruff format --check" ruff format --check "${REPO_ROOT}"
    run_check "ruff check" ruff check "${REPO_ROOT}"
else
    echo "[MISSING] ruff — install with: pip install ruff" >&2
    status=1
fi

# Collect shell scripts once; reuse for shellcheck and shfmt.
shell_scripts=$(find "${REPO_ROOT}/tools" -type f -name '*.sh')

if [ -n "${shell_scripts}" ]; then
    if command -v shellcheck >/dev/null 2>&1; then
        # shellcheck disable=SC2086  # word splitting is intentional here
        run_check "shellcheck" shellcheck ${shell_scripts}
    else
        echo "[MISSING] shellcheck — install via your package manager" >&2
        status=1
    fi

    if command -v shfmt >/dev/null 2>&1; then
        # shellcheck disable=SC2086
        run_check "shfmt -d" shfmt -ln posix -i 4 -ci -d ${shell_scripts}
    else
        echo "[MISSING] shfmt — install via your package manager" >&2
        status=1
    fi
fi

exit "${status}"
