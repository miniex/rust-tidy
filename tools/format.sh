#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if ! command -v ruff &>/dev/null; then
  echo "ruff not found. Install with: pip install ruff"
  exit 1
fi

ruff format "$REPO_ROOT"
ruff check --fix "$REPO_ROOT"
