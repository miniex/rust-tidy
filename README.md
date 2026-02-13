# rust-tidy

A set of small Python tools to keep Rust projects tidy — sorts Cargo.toml dependencies and lints import ordering.

## Tools

### `toml_dep_sorter.py`

Sorts dependencies in `Cargo.toml` files alphabetically.

- Respects groups separated by comments or blank lines
- Handles multi-line dependency definitions
- Sorts `features` lists and expands to multi-line format when 4+ items
- Preserves section headers (`[dependencies]`, `[dev-dependencies]`, etc.)
- Recursively processes all `Cargo.toml` files (skips `target/`)

```sh
python toml_dep_sorter.py
```

### `import_linter.py`

Checks `use` import ordering in `.rs` files at the module level.

- Detects blank lines within a `use` block without a separating comment
- Detects `use` statements placed after code (`struct`, `fn`, `impl`, etc.)
- Skips scoped imports inside functions and blocks

```sh
python import_linter.py
```

## Development

Format and lint Python code:

```sh
./tools/format.sh
```

Requires [ruff](https://github.com/astral-sh/ruff).
