# rust-tidy

Tidy Rust projects: sort `Cargo.toml` dependencies and lint `use`/`mod`
ordering at the module level.

## Install

```sh
pip install -e '.[dev]'
```

This puts `rust-tidy` on your `$PATH`. Quote the extras (`'.[dev]'`) so shells
like zsh and fish don't try to glob-expand the brackets.

## CLI

### `rust-tidy lint`

Lint module-level `use`/`mod` ordering in `.rs` files.

Within every module scope (the file itself, plus each inline `mod foo { ... }`),
the four declaration kinds — `pub mod`, `mod`, `pub use`, `use` — must:

1. Appear in that order at the top of the scope.
2. Be separated from one another by **exactly one** blank line.
3. Have **no** blank lines within a single group.
4. Be sorted alphabetically by import path within each group.
5. Appear before any code (`struct` / `enum` / `fn` / `impl` / `const` / …) in
   the same scope.

Inline modules are exception-handled: `pub mod foo { ... }` and `mod foo { ... }`
do not end the parent scope's import region, and their bodies are linted
recursively as their own scope. Scoped `use` inside `fn` / `impl` / etc. is
ignored.

```sh
rust-tidy lint                        # lint current directory
rust-tidy lint crates/foo crates/bar  # specific paths
rust-tidy lint --fix                  # auto-fix violations in place
rust-tidy lint --exclude vendor       # additional dirs to skip
rust-tidy lint --color=always         # force color even when piped
```

`--fix` sorts within groups, normalizes blank-line spacing, and reorders
groups in every scope. It is idempotent. Segments that contain an orphan
comment (one separated from any decl by blank lines) are left untouched and
emit a warning so you can resolve them by hand; other segments in the same
file are still fixed.

### `rust-tidy sort`

Sort dependencies in `Cargo.toml` files.

- Block-level sort (respects groups separated by `#` comments / blank lines).
- Multi-line dependency entries.
- Sorts `features = [...]` lists; expands to multi-line at 4+ items.
- Sorts inline-table fields canonically: `version`, `path`, `git`, `branch`,
  `tag`, `rev`, `default-features`, `features`, `optional`, then unknown keys
  alphabetically.
- Handles `[dependencies]`, `[dev-dependencies]`, `[build-dependencies]`,
  `[workspace.dependencies]`, and `[target.'cfg(...)'.dependencies]`.

```sh
rust-tidy sort                # sort the current directory
rust-tidy sort path/to/crate  # specific path
rust-tidy sort --check        # CI mode: emit diff and exit 1 if changes pending
rust-tidy sort --no-diff      # in --check, suppress the diff output
```

Output mirrors `cargo` / `cargo clippy`:

```
    Checking 1 Cargo.toml file(s)
warning: dependencies are not sorted
  --> Cargo.toml:1:1
  |
  |
  = help: run `rust-tidy sort` to fix

--- Cargo.toml
+++ Cargo.toml
@@ -1,3 +1,3 @@
 [dependencies]
+bar = "2"
 foo = "1"
-bar = "2"
error: 1 file(s) need sorting
  = help: run `rust-tidy sort` to fix

    Finished in 0.00s
error: rust-tidy sort produced 1 error, 1 warning
```

## Development

```sh
./tools/format.sh   # ruff format/fix + shfmt for tools/
./tools/lint.sh     # ruff format --check + ruff check + shellcheck + shfmt -d
./tools/test.sh     # pytest
```

The dev scripts are POSIX `sh` and rely on:

- [ruff](https://github.com/astral-sh/ruff) — Python format + lint
- [shellcheck](https://www.shellcheck.net/) — shell static analysis
- [shfmt](https://github.com/mvdan/sh) — shell formatter
- [pytest](https://docs.pytest.org/) — test runner

Configuration:

- `ruff.toml` — Python lint/format
- `.shellcheckrc` — shell lint defaults (`shell=sh`)
- `.editorconfig` — editor defaults
- `pyproject.toml` — package metadata + pytest config

## License

MIT — see [`LICENSE`](LICENSE).
