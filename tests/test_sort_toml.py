import io
from pathlib import Path
from textwrap import dedent

from rust_tidy.diag import Reporter
from rust_tidy.sort_toml import process_toml_content, run


def test_sorts_simple_dependencies():
    src = dedent(
        """\
        [dependencies]
        foo = "1"
        bar = "2"
        """
    )
    out = process_toml_content(src)
    assert out == dedent(
        """\
        [dependencies]
        bar = "2"
        foo = "1"
        """
    )


def test_respects_comment_groups():
    src = dedent(
        """\
        [dependencies]
        # group 1
        zoo = "1"
        ant = "2"
        # group 2
        foo = "3"
        bar = "4"
        """
    )
    out = process_toml_content(src)
    assert out == dedent(
        """\
        [dependencies]
        # group 1
        ant = "2"
        zoo = "1"
        # group 2
        bar = "4"
        foo = "3"
        """
    )


def test_handles_dev_and_workspace_sections():
    src = dedent(
        """\
        [dependencies]
        b = "1"
        a = "1"

        [dev-dependencies]
        z = "1"
        y = "1"

        [workspace.dependencies]
        d = "1"
        c = "1"
        """
    )
    out = process_toml_content(src)
    assert '[dependencies]\na = "1"\nb = "1"' in out
    assert '[dev-dependencies]\ny = "1"\nz = "1"' in out
    assert '[workspace.dependencies]\nc = "1"\nd = "1"' in out


def test_target_cfg_dependencies():
    src = dedent(
        """\
        [target.'cfg(unix)'.dependencies]
        b = "1"
        a = "1"
        """
    )
    out = process_toml_content(src)
    assert 'a = "1"\nb = "1"' in out


def test_does_not_touch_non_deps_table():
    src = dedent(
        """\
        [workspace.dependencies.foo]
        version = "1"
        features = ["b", "a"]
        """
    )
    out = process_toml_content(src)
    assert out == src


def test_sorts_inline_table_keys_to_canonical_order():
    src = dedent(
        """\
        [dependencies]
        foo = { default-features = false, features = ["a"], version = "1.0" }
        """
    )
    out = process_toml_content(src)
    assert 'foo = { version = "1.0", default-features = false, features = ["a"] }' in out


def test_sorts_features_list_within_inline_table():
    src = dedent(
        """\
        [dependencies]
        foo = { version = "1", features = ["b", "a", "c"] }
        """
    )
    out = process_toml_content(src)
    assert 'features = ["a", "b", "c"]' in out


def test_expands_long_features_to_multiline():
    src = dedent(
        """\
        [dependencies]
        foo = { version = "1", features = ["b", "a", "c", "d"] }
        """
    )
    out = process_toml_content(src)
    assert '    "a",\n    "b",\n    "c",\n    "d"' in out


def test_idempotent():
    src = dedent(
        """\
        [dependencies]
        a = "1"
        b = { default-features = false, features = ["x", "y"], version = "2" }
        """
    )
    once = process_toml_content(src)
    twice = process_toml_content(once)
    assert once == twice


def test_run_check_returns_1_when_changes_needed(tmp_path: Path):
    f = tmp_path / "Cargo.toml"
    f.write_text('[dependencies]\nfoo = "1"\nbar = "2"\n')
    r = Reporter(stream=io.StringIO(), color_mode="never")
    code = run([tmp_path], r, check=True, show_diff=False)
    assert code == 1
    # File untouched in --check mode
    assert f.read_text() == '[dependencies]\nfoo = "1"\nbar = "2"\n'


def test_run_writes_changes_when_not_check(tmp_path: Path):
    f = tmp_path / "Cargo.toml"
    f.write_text('[dependencies]\nfoo = "1"\nbar = "2"\n')
    r = Reporter(stream=io.StringIO(), color_mode="never")
    code = run([tmp_path], r)
    assert code == 0
    assert "bar" in f.read_text().splitlines()[1]


def test_run_check_returns_0_when_already_sorted(tmp_path: Path):
    f = tmp_path / "Cargo.toml"
    f.write_text('[dependencies]\nbar = "1"\nfoo = "2"\n')
    r = Reporter(stream=io.StringIO(), color_mode="never")
    code = run([tmp_path], r, check=True, show_diff=False)
    assert code == 0
