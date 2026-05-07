"""Cargo/clippy-style diagnostic reporter."""

from __future__ import annotations

import difflib
import os
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Literal

Severity = Literal["error", "warning", "note", "help"]


@dataclass
class Span:
    file: Path
    line: int
    column: int = 1
    span_len: int = 1
    snippet: str | None = None


@dataclass
class Diagnostic:
    severity: Severity
    message: str
    span: Span | None = None
    notes: list[str] = field(default_factory=list)
    helps: list[str] = field(default_factory=list)


class Style:
    """ANSI styling, no-op when disabled."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def _wrap(self, code: str, s: str) -> str:
        return f"\x1b[{code}m{s}\x1b[0m" if self.enabled else s

    def red(self, s: str) -> str:
        return self._wrap("1;31", s)

    def green(self, s: str) -> str:
        return self._wrap("1;32", s)

    def yellow(self, s: str) -> str:
        return self._wrap("1;33", s)

    def blue(self, s: str) -> str:
        return self._wrap("1;34", s)

    def cyan(self, s: str) -> str:
        return self._wrap("1;36", s)

    def bold(self, s: str) -> str:
        return self._wrap("1", s)

    def dim(self, s: str) -> str:
        return self._wrap("2", s)


def color_enabled(stream: IO, mode: str = "auto") -> bool:
    if mode == "always":
        return True
    if mode == "never":
        return False
    if os.environ.get("NO_COLOR"):
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


def _sev_color(style: Style, sev: Severity) -> str:
    s = sev + ":"
    return {
        "error": style.red(s),
        "warning": style.yellow(s),
        "note": style.cyan(s),
        "help": style.green(s),
    }[sev]


def _sev_underline(style: Style, sev: Severity, s: str) -> str:
    return {
        "error": style.red(s),
        "warning": style.yellow(s),
        "note": style.cyan(s),
        "help": style.green(s),
    }[sev]


class Reporter:
    """Stream-based reporter that mirrors cargo/clippy output."""

    def __init__(self, stream: IO = sys.stderr, color_mode: str = "auto") -> None:
        self.stream = stream
        self.style = Style(color_enabled(stream, color_mode))
        self.errors = 0
        self.warnings = 0

    def emit(self, diag: Diagnostic) -> None:
        if diag.severity == "error":
            self.errors += 1
        elif diag.severity == "warning":
            self.warnings += 1

        st = self.style
        sev_lbl = _sev_color(st, diag.severity)
        out = [f"{sev_lbl} {st.bold(diag.message)}"]

        if diag.span:
            sp = diag.span
            line_no = str(sp.line)
            gutter = " " * (len(line_no) + 1)
            loc = f"{sp.file}:{sp.line}:{sp.column}"
            out.append(f"{gutter}{st.blue('-->')} {loc}")
            out.append(f"{gutter}{st.blue('|')}")
            if sp.snippet is not None:
                out.append(f" {st.blue(line_no)} {st.blue('|')} {sp.snippet}")
                pad = " " * max(0, sp.column - 1)
                under = _sev_underline(st, diag.severity, "^" * max(1, sp.span_len))
                out.append(f"{gutter}{st.blue('|')} {pad}{under}")
            out.append(f"{gutter}{st.blue('|')}")

        for n in diag.notes:
            out.append(f"  {st.blue('=')} {st.bold('note:')} {n}")
        for h in diag.helps:
            out.append(f"  {st.blue('=')} {st.bold('help:')} {h}")

        out.append("")
        self.stream.write("\n".join(out) + "\n")

    def action(self, verb: str, message: str) -> None:
        """Cargo-style status line: right-aligned green verb + message."""
        self.stream.write(f"{self.style.green(verb.rjust(12))} {message}\n")

    def note_action(self, verb: str, message: str) -> None:
        """Like action() but in cyan (less prominent than green 'progress')."""
        self.stream.write(f"{self.style.cyan(verb.rjust(12))} {message}\n")

    def summary(self, name: str = "rust-tidy") -> None:
        st = self.style
        if self.errors:
            parts = [
                f"{self.errors} error" + ("s" if self.errors > 1 else ""),
            ]
            if self.warnings:
                parts.append(f"{self.warnings} warning" + ("s" if self.warnings > 1 else ""))
            self.stream.write(f"{st.red('error:')} {name} produced {', '.join(parts)}\n")
        elif self.warnings:
            self.stream.write(
                f"{st.yellow('warning:')} {name} produced "
                f"{self.warnings} warning" + ("s" if self.warnings > 1 else "") + "\n"
            )

    def diff(self, old: str, new: str, label: str) -> None:
        st = self.style
        for line in difflib.unified_diff(
            old.splitlines(keepends=False),
            new.splitlines(keepends=False),
            fromfile=label,
            tofile=label,
            n=3,
            lineterm="",
        ):
            if line.startswith("+++") or line.startswith("---"):
                self.stream.write(st.bold(line) + "\n")
            elif line.startswith("@@"):
                self.stream.write(st.cyan(line) + "\n")
            elif line.startswith("+"):
                self.stream.write(st.green(line) + "\n")
            elif line.startswith("-"):
                self.stream.write(st.red(line) + "\n")
            else:
                self.stream.write(line + "\n")


@contextmanager
def timed(reporter: Reporter, verb: str = "Finished") -> Iterator[None]:
    """Emit a cargo-style 'Finished in 0.05s' line on context exit."""
    start = time.monotonic()
    try:
        yield
    finally:
        elapsed = time.monotonic() - start
        reporter.action(verb, f"in {elapsed:.2f}s")
