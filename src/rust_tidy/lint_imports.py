"""Rust use/mod ordering linter.

Rules (apply within every module scope — top-level file or inline `mod foo { ... }`):
1. Declaration order: pub mod -> mod -> pub use -> use.
2. Exactly one blank line between groups.
3. No blank lines within a group.
4. Within a group, declarations are sorted alphabetically by import path.
5. None of these declarations may appear after code in the same scope.

Inline modules `pub mod foo { ... }` and `mod foo { ... }` are exception-handled:
they don't end the parent's import region and are not part of the parent's groups.
Their bodies are linted recursively as their own scope.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from rust_tidy.diag import Diagnostic, Reporter, Span

DEFAULT_EXCLUDE_DIRS = frozenset({"target", ".git", ".cargo", "node_modules"})

GROUP_PUB_MOD = 0
GROUP_MOD = 1
GROUP_PUB_USE = 2
GROUP_USE = 3
GROUP_NAMES = {
    GROUP_PUB_MOD: "pub mod",
    GROUP_MOD: "mod",
    GROUP_PUB_USE: "pub use",
    GROUP_USE: "use",
}

PUB_MOD_RE = re.compile(r"^\s*pub(\s*\([^)]*\))?\s+mod\s+\w+\s*;\s*$")
MOD_RE = re.compile(r"^\s*mod\s+\w+\s*;\s*$")
PUB_USE_RE = re.compile(r"^\s*pub(\s*\([^)]*\))?\s+use\s+")
USE_RE = re.compile(r"^\s*use\s+")
INLINE_MOD_RE = re.compile(r"^\s*(pub(\s*\([^)]*\))?\s+)?mod\s+\w+\s*\{")
CODE_RE = re.compile(r"^\s*(pub(\s*\([^)]*\))?\s*)?(struct|enum|type|trait|impl|fn)\b")
CONST_RE = re.compile(r"^\s*(pub(\s*\([^)]*\))?\s*)?(const|static)\s+")
MACRO_RE = re.compile(r"^\s*\w+!")
ATTR_RE = re.compile(r"^\s*#")
COMMENT_RE = re.compile(r"^\s*//")

_KW_PUB_RE = re.compile(r"^\s*pub(\s*\([^)]*\))?\s+(mod|use)\b")
_KW_SIMPLE_RE = re.compile(r"^\s*(mod|use)\b")
_PATH_END_RE = re.compile(r"\s+as\s+|::\{|\{|;|$")


def _count_braces(stripped: str) -> tuple[int, int]:
    in_string = in_char = False
    opens = closes = 0
    prev = ""
    for ch in stripped:
        if ch == '"' and prev != "\\" and not in_char:
            in_string = not in_string
        elif ch == "'" and prev != "\\" and not in_string:
            in_char = not in_char
        elif not in_string and not in_char:
            if ch == "{":
                opens += 1
            elif ch == "}":
                closes += 1
        prev = ch
    return opens, closes


def _classify(line: str) -> int | str | None:
    """Classify a module-level line. Group decls return their group index;
    "inline_mod" / "code" / None otherwise."""
    if INLINE_MOD_RE.match(line):
        opens, closes = _count_braces(line.strip())
        if opens > closes:
            return "inline_mod"
        # `mod foo {}` on a single line: transparent, no body to recurse into.
        return "inline_mod_oneliner"
    if PUB_MOD_RE.match(line):
        return GROUP_PUB_MOD
    if MOD_RE.match(line):
        return GROUP_MOD
    if PUB_USE_RE.match(line):
        return GROUP_PUB_USE
    if USE_RE.match(line):
        return GROUP_USE
    if CODE_RE.match(line) or CONST_RE.match(line) or MACRO_RE.match(line):
        return "code"
    return None


def _extract_sort_key(decl: str) -> str:
    s = decl.lstrip()
    if s.startswith("pub"):
        s = s[3:].lstrip()
        if s.startswith("("):
            close = s.find(")")
            if close != -1:
                s = s[close + 1 :].lstrip()
    if s.startswith(("use ", "mod ")):
        s = s[4:]
    s = s.lstrip()
    m = _PATH_END_RE.search(s)
    if m:
        s = s[: m.start()]
    return s.strip().lower()


def _kw_span(decl: str, group: int) -> tuple[int, int]:
    """Return (1-based column, length) underlining the leading keyword."""
    column = (len(decl) - len(decl.lstrip())) + 1
    if group in (GROUP_PUB_MOD, GROUP_PUB_USE):
        m = _KW_PUB_RE.match(decl)
        if m:
            return column, m.end() - (column - 1)
    else:
        m = _KW_SIMPLE_RE.match(decl)
        if m:
            return column, m.end() - (column - 1)
    return column, 1


def _find_matching_brace(lines: list[str], start: int, end: int) -> int:
    """Return the line index where the brace opened on `start` is closed.

    Falls back to `end - 1` if no match is found within the slice.
    """
    depth = 0
    started = False
    for i in range(start, end):
        opens, closes = _count_braces(lines[i].strip())
        if not started:
            if opens > 0:
                depth = opens - closes
                started = True
                if depth <= 0:
                    return i
            continue
        depth += opens - closes
        if depth <= 0:
            return i
    return end - 1


@dataclass
class ImportBlock:
    group: int
    preamble: list[str]
    decl_lines: list[str]
    preamble_start: int
    decl_line: int
    blanks_before: int
    sort_key: str = ""

    def __post_init__(self) -> None:
        self.sort_key = _extract_sort_key(self.decl_lines[0])

    @property
    def end_index(self) -> int:
        return (self.decl_line - 1) + len(self.decl_lines)


@dataclass
class Segment:
    """A contiguous run of import blocks within one module scope."""

    blocks: list[ImportBlock]
    region_start: int
    region_end: int
    fixable: bool = True
    fix_blocker_line: int = -1


@dataclass
class ScopeResult:
    segments: list[Segment] = field(default_factory=list)
    sub_scopes: list[ScopeResult] = field(default_factory=list)
    code_first_line: int = -1


def parse_scope(lines: list[str], start: int = 0, end: int | None = None) -> ScopeResult:
    """Parse `lines[start:end]` as a single module scope.

    Inline modules nest: their bodies become entries in `sub_scopes`. Code
    bodies (fn/impl/...) are skipped without recursion.
    """
    if end is None:
        end = len(lines)

    scope = ScopeResult()
    cur_blocks: list[ImportBlock] = []
    cur_region_start = -1
    cur_fixable = True
    cur_fix_blocker = -1

    pending_preamble: list[str] = []
    pending_preamble_start = -1
    blanks_since = 0
    seen_first_decl = False
    in_ml_decl = False

    def flush_segment() -> None:
        nonlocal cur_blocks, cur_region_start, cur_fixable, cur_fix_blocker
        if cur_blocks:
            scope.segments.append(
                Segment(
                    blocks=cur_blocks,
                    region_start=cur_region_start,
                    region_end=cur_blocks[-1].end_index,
                    fixable=cur_fixable,
                    fix_blocker_line=cur_fix_blocker,
                )
            )
        cur_blocks = []
        cur_region_start = -1
        cur_fixable = True
        cur_fix_blocker = -1

    i = start
    while i < end:
        line = lines[i]
        stripped = line.strip()

        if in_ml_decl:
            cur_blocks[-1].decl_lines.append(line)
            if ";" in stripped:
                in_ml_decl = False
            i += 1
            continue

        if not stripped:
            if pending_preamble and seen_first_decl:
                cur_fixable = False
                if cur_fix_blocker == -1:
                    cur_fix_blocker = pending_preamble_start + 1
            pending_preamble = []
            pending_preamble_start = -1
            blanks_since += 1
            i += 1
            continue

        if scope.code_first_line == -1 and (COMMENT_RE.match(stripped) or ATTR_RE.match(stripped)):
            if not pending_preamble:
                pending_preamble_start = i
            pending_preamble.append(line)
            i += 1
            continue

        kind = _classify(line)

        if kind == "inline_mod":
            # Inline module with a body: recurse, treat as transparent fence.
            flush_segment()
            close = _find_matching_brace(lines, i, end)
            sub = parse_scope(lines, i + 1, close)
            scope.sub_scopes.append(sub)
            pending_preamble = []
            pending_preamble_start = -1
            blanks_since = 0
            i = close + 1
            continue

        if kind == "inline_mod_oneliner":
            # `mod foo {}` on one line: transparent, no body.
            flush_segment()
            pending_preamble = []
            pending_preamble_start = -1
            blanks_since = 0
            opens, closes = _count_braces(stripped)
            if opens > closes:
                close = _find_matching_brace(lines, i, end)
                i = close + 1
            else:
                i += 1
            continue

        if kind in (GROUP_PUB_MOD, GROUP_MOD, GROUP_PUB_USE, GROUP_USE):
            preamble_start = pending_preamble_start if pending_preamble else i
            block = ImportBlock(
                group=kind,
                preamble=pending_preamble[:],
                decl_lines=[line],
                preamble_start=preamble_start,
                decl_line=i + 1,
                blanks_before=blanks_since,
            )
            cur_blocks.append(block)
            if cur_region_start == -1:
                cur_region_start = preamble_start
            pending_preamble = []
            pending_preamble_start = -1
            blanks_since = 0
            seen_first_decl = True
            if "{" in stripped and ";" not in stripped:
                in_ml_decl = True
            i += 1
            continue

        # "code" or unknown: end any open segment, skip body if it has braces.
        if kind == "code" and scope.code_first_line == -1:
            scope.code_first_line = i + 1
        flush_segment()
        pending_preamble = []
        pending_preamble_start = -1
        blanks_since = 0
        opens, closes = _count_braces(stripped)
        if opens > closes:
            close = _find_matching_brace(lines, i, end)
            i = close + 1
        else:
            i += 1

    flush_segment()
    return scope


def _diag_kw(path: Path, block: ImportBlock, severity: str, msg: str, **kw) -> Diagnostic:
    decl = block.decl_lines[0]
    col, length = _kw_span(decl, block.group)
    return Diagnostic(
        severity=severity,  # type: ignore[arg-type]
        message=msg,
        span=Span(file=path, line=block.decl_line, column=col, span_len=length, snippet=decl),
        **kw,
    )


def _lint_segment(path: Path, segment: Segment, code_first_line: int) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    last_group: int | None = None
    last_in_group: ImportBlock | None = None

    for idx, block in enumerate(segment.blocks):
        if code_first_line > 0 and block.decl_line > code_first_line:
            diags.append(
                _diag_kw(
                    path,
                    block,
                    "error",
                    f"'{GROUP_NAMES[block.group]}' declaration after code",
                    notes=[f"first code definition at {path}:{code_first_line}"],
                )
            )
            continue

        if last_group is None:
            last_group = block.group
            last_in_group = block
            continue

        if block.group == last_group:
            if block.blanks_before > 0:
                blank_line = block.preamble_start - block.blanks_before + 1
                diags.append(
                    Diagnostic(
                        severity="error",
                        message=f"blank line within '{GROUP_NAMES[block.group]}' group",
                        span=Span(
                            file=path,
                            line=blank_line,
                            column=1,
                            span_len=1,
                            snippet="",
                        ),
                        helps=["remove the blank line so the group is contiguous"],
                    )
                )
            if last_in_group is not None and block.sort_key < last_in_group.sort_key:
                diags.append(
                    _diag_kw(
                        path,
                        block,
                        "warning",
                        f"'{GROUP_NAMES[block.group]}' declarations are not alphabetically sorted",
                        notes=[f"'{block.sort_key}' should sort before '{last_in_group.sort_key}'"],
                        helps=["run `rust-tidy lint --fix` to sort"],
                    )
                )
            last_in_group = block
        elif block.group > last_group:
            if block.blanks_before == 0:
                diags.append(
                    _diag_kw(
                        path,
                        block,
                        "error",
                        f"missing blank line before '{GROUP_NAMES[block.group]}' group",
                        helps=["insert a single blank line between groups"],
                    )
                )
            elif block.blanks_before > 1 and idx > 0:
                diags.append(
                    _diag_kw(
                        path,
                        block,
                        "error",
                        f"expected one blank line before "
                        f"'{GROUP_NAMES[block.group]}' group, found "
                        f"{block.blanks_before}",
                        helps=["collapse to a single blank line"],
                    )
                )
            last_group = block.group
            last_in_group = block
        else:
            diags.append(
                _diag_kw(
                    path,
                    block,
                    "error",
                    f"'{GROUP_NAMES[block.group]}' must appear before "
                    f"'{GROUP_NAMES[last_group]}' group",
                    helps=[
                        f"move this above the '{GROUP_NAMES[last_group]}' group "
                        f"or run `rust-tidy lint --fix`"
                    ],
                )
            )
            last_group = block.group
            last_in_group = block

    return diags


def lint_diagnostics(path: Path, scope: ScopeResult) -> list[Diagnostic]:
    """Recursively lint a scope and all its inline-module sub-scopes."""
    diags: list[Diagnostic] = []
    for segment in scope.segments:
        diags.extend(_lint_segment(path, segment, scope.code_first_line))
    for sub in scope.sub_scopes:
        diags.extend(lint_diagnostics(path, sub))
    return diags


def _emit_fixed_region(blocks: list[ImportBlock]) -> list[str]:
    sorted_blocks = sorted(blocks, key=lambda b: (b.group, b.sort_key, b.decl_line))
    out: list[str] = []
    last_group: int | None = None
    for block in sorted_blocks:
        if last_group is not None and block.group != last_group:
            out.append("")
        out.extend(block.preamble)
        out.extend(block.decl_lines)
        last_group = block.group
    return out


def _collect_fixable_segments(scope: ScopeResult, out: list[Segment]) -> None:
    for seg in scope.segments:
        if seg.fixable:
            out.append(seg)
    for sub in scope.sub_scopes:
        _collect_fixable_segments(sub, out)


def _collect_blockers(scope: ScopeResult, out: list[Segment]) -> None:
    for seg in scope.segments:
        if not seg.fixable:
            out.append(seg)
    for sub in scope.sub_scopes:
        _collect_blockers(sub, out)


def fix_text(text: str) -> tuple[str, ScopeResult]:
    """Return (new_text, parse_result). new_text == text if no change."""
    keepends = text.endswith(("\n", "\r\n"))
    lines = text.splitlines()
    scope = parse_scope(lines)

    fixable: list[Segment] = []
    _collect_fixable_segments(scope, fixable)
    # Apply replacements bottom-up so earlier indices stay valid.
    fixable.sort(key=lambda s: s.region_start, reverse=True)

    new_lines = list(lines)
    for seg in fixable:
        new_region = _emit_fixed_region(seg.blocks)
        new_lines[seg.region_start : seg.region_end] = new_region

    new_text = "\n".join(new_lines)
    if keepends:
        new_text += "\n"
    return new_text, scope


def lint_file(
    path: Path,
    reporter: Reporter,
    fix: bool = False,
) -> int:
    """Lint one file. Returns count of remaining (unfixed) errors."""
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return 0

    if fix:
        new_text, scope = fix_text(text)
        blockers: list[Segment] = []
        _collect_blockers(scope, blockers)
        for seg in blockers:
            if seg.fix_blocker_line > 0:
                reporter.emit(
                    Diagnostic(
                        severity="warning",
                        message="cannot auto-fix: orphan comment/attr in import region",
                        span=Span(
                            file=path,
                            line=seg.fix_blocker_line,
                            column=1,
                            span_len=1,
                        ),
                        helps=[
                            "remove the blank line(s) around the comment, then re-run",
                        ],
                    )
                )
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
            reporter.action("Fixed", str(path))
            text = new_text

    scope = parse_scope(text.splitlines())
    diags = lint_diagnostics(path, scope)
    err_count = 0
    for d in diags:
        reporter.emit(d)
        if d.severity == "error":
            err_count += 1
    return err_count


def iter_rust_files(roots: list[Path], exclude: frozenset[str]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if root.is_file():
            if root.suffix == ".rs":
                files.append(root)
            continue
        for path in root.rglob("*.rs"):
            if any(part in exclude for part in path.parts):
                continue
            files.append(path)
    return files


def run(
    paths: list[Path],
    reporter: Reporter,
    *,
    exclude: frozenset[str] = DEFAULT_EXCLUDE_DIRS,
    fix: bool = False,
) -> int:
    files = iter_rust_files(paths, exclude)
    reporter.action("Checking", f"{len(files)} Rust file(s)")
    for f in files:
        lint_file(f, reporter, fix=fix)
    return 1 if reporter.errors > 0 else 0
