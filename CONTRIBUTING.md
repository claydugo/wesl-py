# Contributing

Open an [issue](https://github.com/claydugo/wesl-py/issues) with a small reproducer,
expected behavior, errors, and Python and wesl-py versions.
Include your OS and, for GPU failures, the adapter and backend.
Discuss larger changes before starting.

## Set up a checkout

Install [Pixi](https://pixi.sh) 0.80 or later.
Development supports Linux x86-64, macOS arm64, and Windows x86-64.
Pixi supplies Python, Rust, Maturin, and an editable wesl-py installation.
Source builds require Rust 1.97.1 or later and a native linker.

```bash
git clone https://github.com/claydugo/wesl-py.git
cd wesl-py
pixi install --locked -e test
pixi run -e test python -m pytest tests/test_check_syntax.py -q
pixi run --locked -e lint prek install
```

The test needs no GPU. Run commands from the repository root.
Git hooks require Pixi on `PATH`. Review and stage formatter fixes before retrying.
For Jujutsu, run the checks below explicitly.

Python edits take effect immediately. After Rust edits, rebuild in your environment:

```bash
pixi reinstall --locked -e test wesl-py
```

Replace `test` with `gpu`, `testing`, or `dev` as needed.

## Verify your change

Run the tests that cover your change:

```bash
pixi run -e test python -m pytest tests/test_compile.py -q
```

| Environment | Use |
| --- | --- |
| `test` | Compiler and Python tests without GPU dependencies |
| `gpu` | Generated WGSL execution with NumPy and wgpu-py |
| `testing` | Shader executor, pytest plugin, and examples |

Each [example](examples/README.md) lists its test command.
See the [testing examples](tests/examples/testing/README.md) for snapshot updates.
For viewer changes, run the affected offscreen tests and verify controls and resizing
in the window.

For code changes, also run:

```bash
pixi run lint
pixi run check-rust
pixi run check-types
```

`lint` checks without changing files. `pixi run format` applies formatter fixes.
`check-rust` runs rustfmt and Clippy. `check-types` runs ty, Pyrefly, Pyright,
and native stubtest. These checks need no GPU adapter.
Run `pixi run generate-stubs` after changing a native signature.
Use `gen_stub` attributes for types that PyO3 erases.

For Rust dependency changes, run `pixi run check-dependencies`.
For prose changes, verify Markdown, links, and affected commands.
[prek.toml](prek.toml) defines hooks. [pixi.toml](pixi.toml) defines tasks.

## Edit shaders

Configure your editor to use the nearest `wesl.toml` as the wgsl-analyzer root.
See [shader editing](docs/testing.md#shader-editing) for other projects.

## Write documentation

Lead with the command or fact the reader needs. Keep prose short and direct.
Explain each behavior in one place and link to it elsewhere.
Omit code walkthroughs and tool internals unless they help the reader act.
Do not maintain directory maps, file inventories, or copies of configuration.
Use sentence case for headings, 80 columns for prose, and 88 for code blocks.

## Open a pull request

Describe the problem, resulting behavior, and checks you run.
Keep the change focused. Add a regression test for a behavior defect.
Update the relevant guide or example when changing the public API.

[CI](.github/workflows/artifacts.yml) checks source, editable installs, and wheels.
See the [release checklist](RELEASE_CHECKLIST.md) for publication and
[upstream notes](docs/upstream.md) before updating dependencies.
