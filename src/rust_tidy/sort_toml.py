"""Sort dependency entries in Cargo.toml files.

Handles `[dependencies]`, `[dev-dependencies]`, `[build-dependencies]`,
`[workspace.dependencies]`, and `[target.'cfg(...)'.dependencies]`.
"""

from __future__ import annotations

import re
from pathlib import Path

from rust_tidy.diag import Diagnostic, Reporter, Span

DEFAULT_EXCLUDE_DIRS = frozenset({"target", ".git", "node_modules"})

# Match section headers ending with `dependencies]` so we don't accidentally
# touch `[workspace.dependencies.foo]` (a single dep's own table).
SECTION_SPLIT_RE = re.compile(r"(\[[^\]]*dependencies\])")
NEXT_SECTION_RE = re.compile(r"\n\[")
FEATURES_RE = re.compile(r"(features\s*=\s*\[)([^\]]+)(\])", flags=re.DOTALL)

# Canonical inline-table key order (anything else sorts after, alphabetically).
INLINE_KEY_ORDER = [
    "workspace",
    "package",
    "version",
    "path",
    "git",
    "branch",
    "tag",
    "rev",
    "registry",
    "default-features",
    "features",
    "optional",
]
INLINE_KEY_RANK = {k: i for i, k in enumerate(INLINE_KEY_ORDER)}


def _key_rank(key: str) -> tuple[int, str]:
    return INLINE_KEY_RANK.get(key, len(INLINE_KEY_ORDER)), key


def _find_top_braces(unit: str) -> tuple[int, int] | None:
    """Locate the first balanced top-level `{...}` span in `unit`."""
    depth = 0
    start = -1
    in_str = False
    quote = ""
    prev = ""
    for i, ch in enumerate(unit):
        if in_str:
            if ch == quote and prev != "\\":
                in_str = False
            prev = ch
            continue
        if ch in "\"'":
            in_str = True
            quote = ch
            prev = ch
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                return start, i + 1
        prev = ch
    return None


def _split_pairs(content: str) -> list[tuple[str, str]] | None:
    """Split inline-table content into (key, value) pairs.

    Respects nested `[]`, `{}`, and string literals.
    Returns None if the content cannot be parsed.
    """
    parts: list[str] = []
    cur: list[str] = []
    depth = 0
    in_str = False
    quote = ""
    prev = ""
    for ch in content:
        if in_str:
            cur.append(ch)
            if ch == quote and prev != "\\":
                in_str = False
            prev = ch
            continue
        if ch in "\"'":
            cur.append(ch)
            in_str = True
            quote = ch
            prev = ch
            continue
        if ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        if ch == "," and depth == 0:
            text = "".join(cur).strip()
            if text:
                parts.append(text)
            cur = []
            prev = ch
            continue
        cur.append(ch)
        prev = ch
    tail = "".join(cur).strip()
    if tail:
        parts.append(tail)

    pairs: list[tuple[str, str]] = []
    for p in parts:
        eq = -1
        d = 0
        s = False
        q = ""
        pr = ""
        for i, ch in enumerate(p):
            if s:
                if ch == q and pr != "\\":
                    s = False
            elif ch in "\"'":
                s = True
                q = ch
            elif ch in "[{":
                d += 1
            elif ch in "]}":
                d -= 1
            elif ch == "=" and d == 0:
                eq = i
                break
            pr = ch
        if eq == -1:
            return None
        key = p[:eq].strip()
        val = p[eq + 1 :].strip()
        pairs.append((key, val))
    return pairs


def _sort_inline_table(unit: str) -> str:
    span = _find_top_braces(unit)
    if span is None:
        return unit
    start, end = span
    inner = unit[start + 1 : end - 1]
    pairs = _split_pairs(inner)
    if pairs is None or len(pairs) < 2:
        return unit
    sorted_pairs = sorted(pairs, key=lambda p: _key_rank(p[0]))
    if sorted_pairs == pairs:
        return unit
    multiline = "\n" in inner
    if multiline:
        body = ",\n".join(f"    {k} = {v}" for k, v in sorted_pairs)
        new_inner = f"\n{body},\n"
    else:
        body = ", ".join(f"{k} = {v}" for k, v in sorted_pairs)
        new_inner = f" {body} "
    return unit[:start] + "{" + new_inner + "}" + unit[end:]


def _format_features(match: re.Match[str]) -> str:
    prefix, content, suffix = match.group(1), match.group(2), match.group(3)
    items = sorted(i.strip() for i in content.split(",") if i.strip())
    if len(items) >= 4:
        return f"{prefix}\n    " + ",\n    ".join(items) + f"\n{suffix}"
    return f"{prefix}{', '.join(items)}{suffix}"


def sort_block(lines: list[str]) -> list[str]:
    if not lines:
        return []
    units: list[str] = []
    current: list[str] = []
    bracket = 0
    for line in lines:
        current.append(line)
        bracket += line.count("[") - line.count("]")
        if bracket <= 0 and line.strip():
            unit = "\n".join(current)
            unit = _sort_inline_table(unit)
            unit = FEATURES_RE.sub(_format_features, unit)
            units.append(unit)
            current = []
    if current:
        units.append("\n".join(current))
    units.sort(key=lambda x: x.strip().lower())
    return [line for u in units for line in u.splitlines()]


def process_toml_content(content: str) -> str:
    sections = SECTION_SPLIT_RE.split(content)
    for i in range(1, len(sections), 2):
        body = sections[i + 1]
        m = NEXT_SECTION_RE.search(body)
        if m:
            main_body = body[: m.start()]
            tail = body[m.start() :]
        else:
            main_body = body
            tail = ""
        new_body: list[str] = []
        current: list[str] = []
        bracket = 0
        for line in main_body.splitlines():
            stripped = line.strip()
            if bracket == 0 and (stripped.startswith("#") or not stripped):
                if current:
                    new_body.extend(sort_block(current))
                    current = []
                new_body.append(line)
            else:
                current.append(line)
                bracket += line.count("[") - line.count("]")
        if current:
            new_body.extend(sort_block(current))
        formatted = "\n".join(new_body).rstrip()
        if tail.strip() or (i + 2 < len(sections)):
            formatted += "\n\n"
        else:
            formatted += "\n"
        sections[i + 1] = formatted + tail
    return "".join(sections)


def iter_cargo_tomls(roots: list[Path], exclude: frozenset[str]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if root.is_file():
            if root.name == "Cargo.toml":
                files.append(root)
            continue
        for path in root.rglob("Cargo.toml"):
            if any(part in exclude for part in path.parts):
                continue
            files.append(path)
    return files


def run(
    paths: list[Path],
    reporter: Reporter,
    *,
    exclude: frozenset[str] = DEFAULT_EXCLUDE_DIRS,
    check: bool = False,
    show_diff: bool = True,
) -> int:
    files = iter_cargo_tomls(paths, exclude)
    verb = "Checking" if check else "Sorting"
    reporter.action(verb, f"{len(files)} Cargo.toml file(s)")

    needs_sort = 0
    for path in files:
        try:
            old = path.read_text(encoding="utf-8")
        except OSError as e:
            reporter.emit(Diagnostic(severity="error", message=f"could not read {path}: {e}"))
            return 2
        new = process_toml_content(old)
        if old == new:
            continue
        needs_sort += 1
        if check:
            reporter.emit(
                Diagnostic(
                    severity="warning",
                    message="dependencies are not sorted",
                    span=Span(file=path, line=1, column=1, span_len=1),
                    helps=["run `rust-tidy sort` to fix"],
                )
            )
            if show_diff:
                reporter.diff(old, new, str(path))
        else:
            try:
                path.write_text(new, encoding="utf-8")
            except OSError as e:
                reporter.emit(Diagnostic(severity="error", message=f"could not write {path}: {e}"))
                return 2
            reporter.action("Sorted", str(path))

    if check and needs_sort > 0:
        reporter.emit(
            Diagnostic(
                severity="error",
                message=f"{needs_sort} file(s) need sorting",
                helps=["run `rust-tidy sort` to fix"],
            )
        )
        return 1
    return 0
