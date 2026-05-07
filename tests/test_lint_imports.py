from pathlib import Path
from textwrap import dedent

from rust_tidy.diag import Reporter
from rust_tidy.lint_imports import fix_text, lint_diagnostics, parse_scope


def _parse(src: str):
    return parse_scope(src.splitlines())


def test_clean_file_has_no_diagnostics(tmp_path: Path):
    src = dedent(
        """\
        pub mod a;
        pub mod b;

        mod c;

        pub use foo::Bar;

        use baz::Qux;

        fn main() {}
        """
    )
    diags = lint_diagnostics(tmp_path / "ok.rs", _parse(src))
    assert diags == []


def test_out_of_order_flagged(tmp_path: Path):
    src = "mod c;\n\npub mod a;\n"
    diags = lint_diagnostics(tmp_path / "f.rs", _parse(src))
    assert any("must appear before" in d.message for d in diags)


def test_missing_blank_between_groups(tmp_path: Path):
    src = "pub mod a;\nmod b;\n"
    diags = lint_diagnostics(tmp_path / "f.rs", _parse(src))
    assert any("missing blank line" in d.message for d in diags)


def test_blank_within_group(tmp_path: Path):
    src = "use foo;\n\nuse bar;\n"
    diags = lint_diagnostics(tmp_path / "f.rs", _parse(src))
    assert any("blank line within" in d.message for d in diags)


def test_alphabetical_within_group(tmp_path: Path):
    src = "use foo;\nuse bar;\n"
    diags = lint_diagnostics(tmp_path / "f.rs", _parse(src))
    assert any("alphabetically sorted" in d.message for d in diags)


def test_use_after_code(tmp_path: Path):
    src = "use foo;\n\nfn main() {}\n\nuse bar;\n"
    diags = lint_diagnostics(tmp_path / "f.rs", _parse(src))
    assert any("after code" in d.message for d in diags)


def test_scoped_use_inside_fn_block_ignored(tmp_path: Path):
    src = dedent(
        """\
        use foo;

        fn main() {
            use bar::Baz;
            use aaa::Zzz;
        }
        """
    )
    diags = lint_diagnostics(tmp_path / "f.rs", _parse(src))
    assert diags == []


def test_inline_mod_does_not_end_outer_region(tmp_path: Path):
    src = dedent(
        """\
        use foo;

        pub mod inline {
            use bar;
        }

        use zoo;
        """
    )
    diags = lint_diagnostics(tmp_path / "f.rs", _parse(src))
    assert not any("after code" in d.message for d in diags)


def test_inline_mod_body_linted_independently(tmp_path: Path):
    src = dedent(
        """\
        pub mod inline {
            use foo;
            use bar;
        }
        """
    )
    diags = lint_diagnostics(tmp_path / "f.rs", _parse(src))
    assert any("alphabetically sorted" in d.message for d in diags)


def test_inline_mod_body_ordering_violations_flagged(tmp_path: Path):
    src = dedent(
        """\
        pub mod inline {
            use foo;

            mod bar;
        }
        """
    )
    diags = lint_diagnostics(tmp_path / "f.rs", _parse(src))
    assert any("must appear before" in d.message for d in diags)


def test_inline_mod_oneliner_does_not_flag(tmp_path: Path):
    src = dedent(
        """\
        use foo;

        pub mod empty {}

        use bar;
        """
    )
    diags = lint_diagnostics(tmp_path / "f.rs", _parse(src))
    assert not any("after code" in d.message for d in diags)


def test_fix_sorts_within_group_and_normalizes_blanks():
    src = dedent(
        """\
        use foo;
        use bar;
        pub mod b;
        pub mod a;
        mod d;
        mod c;
        pub use zoo::Z;
        pub use ant::A;

        fn main() {}
        """
    )
    fixed, _ = fix_text(src)
    assert fixed == dedent(
        """\
        pub mod a;
        pub mod b;

        mod c;
        mod d;

        pub use ant::A;
        pub use zoo::Z;

        use bar;
        use foo;

        fn main() {}
        """
    )


def test_fix_is_idempotent():
    src = dedent(
        """\
        pub mod a;

        mod b;

        use bar;
        use foo;

        fn main() {}
        """
    )
    once, _ = fix_text(src)
    twice, _ = fix_text(once)
    assert once == twice == src


def test_fix_preserves_attached_attrs():
    src = dedent(
        """\
        #[cfg(feature = "x")]
        use zoo;
        #[cfg(test)]
        use ant;
        """
    )
    fixed, _ = fix_text(src)
    expected = dedent(
        """\
        #[cfg(test)]
        use ant;
        #[cfg(feature = "x")]
        use zoo;
        """
    )
    assert fixed == expected


def test_fix_preserves_multiline_use():
    src = dedent(
        """\
        use foo::{
            A,
            B,
        };
        use bar;
        """
    )
    fixed, _ = fix_text(src)
    expected = dedent(
        """\
        use bar;
        use foo::{
            A,
            B,
        };
        """
    )
    assert fixed == expected


def test_fix_skips_when_orphan_comment_present():
    src = dedent(
        """\
        use foo;

        // orphan

        use bar;
        """
    )
    fixed, scope = fix_text(src)
    assert fixed == src
    assert any(not seg.fixable for seg in scope.segments)


def test_fix_inline_mod_body_independently():
    src = dedent(
        """\
        use outer_b;
        use outer_a;

        pub mod inline {
            use inner_b;
            use inner_a;
        }
        """
    )
    fixed, _ = fix_text(src)
    expected = dedent(
        """\
        use outer_a;
        use outer_b;

        pub mod inline {
            use inner_a;
            use inner_b;
        }
        """
    )
    assert fixed == expected


def test_fix_segments_split_by_inline_mod_sort_independently():
    src = dedent(
        """\
        use bbb;
        use aaa;

        pub mod inline {}

        use zzz;
        use yyy;
        """
    )
    fixed, _ = fix_text(src)
    expected = dedent(
        """\
        use aaa;
        use bbb;

        pub mod inline {}

        use yyy;
        use zzz;
        """
    )
    assert fixed == expected


def test_run_emits_no_errors_for_clean_tree(tmp_path: Path):
    f = tmp_path / "ok.rs"
    f.write_text("use foo;\n")
    from rust_tidy.lint_imports import run

    r = Reporter(stream=__import__("io").StringIO(), color_mode="never")
    code = run([tmp_path], r)
    assert code == 0
    assert r.errors == 0
