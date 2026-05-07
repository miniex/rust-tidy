import io
from pathlib import Path

from rust_tidy.diag import Diagnostic, Reporter, Span, color_enabled


def test_color_enabled_modes():
    assert color_enabled(io.StringIO(), "always") is True
    assert color_enabled(io.StringIO(), "never") is False
    # auto on a non-tty stream → False
    assert color_enabled(io.StringIO(), "auto") is False


def test_emit_error_increments_counter():
    r = Reporter(stream=io.StringIO(), color_mode="never")
    r.emit(Diagnostic(severity="error", message="boom"))
    assert r.errors == 1
    assert r.warnings == 0
    out = r.stream.getvalue()  # type: ignore[union-attr]
    assert "error: boom" in out


def test_emit_with_span_renders_snippet():
    buf = io.StringIO()
    r = Reporter(stream=buf, color_mode="never")
    r.emit(
        Diagnostic(
            severity="warning",
            message="bad thing",
            span=Span(
                file=Path("src/foo.rs"), line=5, column=3, span_len=4, snippet="    use bar;"
            ),
            notes=["this is a note"],
            helps=["try this"],
        )
    )
    out = buf.getvalue()
    assert "warning: bad thing" in out
    assert "--> src/foo.rs:5:3" in out
    assert "5 |     use bar;" in out
    assert "= note: this is a note" in out
    assert "= help: try this" in out


def test_diff_renders_unified():
    buf = io.StringIO()
    r = Reporter(stream=buf, color_mode="never")
    r.diff("a\nb\nc\n", "a\nB\nc\n", "file.txt")
    out = buf.getvalue()
    assert "--- file.txt" in out
    assert "+++ file.txt" in out
    assert "-b" in out
    assert "+B" in out


def test_summary_picks_severity():
    buf = io.StringIO()
    r = Reporter(stream=buf, color_mode="never")
    r.emit(Diagnostic(severity="error", message="x"))
    r.emit(Diagnostic(severity="warning", message="y"))
    buf.truncate(0)
    buf.seek(0)
    r.summary("rust-tidy")
    out = buf.getvalue()
    assert "1 error" in out
    assert "1 warning" in out
