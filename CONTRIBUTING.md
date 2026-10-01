# Contributing

Start with the [README](README.md) and [examples](examples/README.md).
Bug reports, documentation, examples, and code contributions are welcome.

## Report a problem or suggest a change

Open an [issue](https://github.com/claydugo/wesl-py/issues) with a small example,
what you expect, and what happens instead.
Include errors, Python and wesl-py versions, and your OS.
For GPU failures, include the adapter and backend.

Report unclear documentation too. Discuss larger changes in an issue first.

## Set up a checkout

Install [Pixi](https://pixi.sh) 0.80 or later.
The development environments support Linux x86-64, macOS arm64, and Windows x86-64.
Pixi provides Python, Rust, Maturin, and an editable installation of wesl-py.
Source builds require Rust 1.97.1 or later and a native linker.

Clone the repository and run a small test file to verify the setup:

```bash
git clone https://github.com/claydugo/wesl-py.git
cd wesl-py
pixi install --locked -e test
pixi run -e test python -m pytest tests/test_check_syntax.py -q
```

This test needs no GPU.
Run the commands below from the repository root.

Install the pre-commit and pre-push hooks:

```bash
pixi run --locked -e lint prek install
```

Pre-commit formats selected files and the Rust crate.
Linters check the repository when relevant files or configuration change.
Shared configuration triggers read-only formatting checks.
Review and stage formatter fixes before retrying.
Pre-push runs Rust and Python type checks for relevant changes, including deletions.
Documentation changes skip these checks.
Stubtest rebuilds the extension before checking its stubs.
Install hooks once per checkout, or again to add pre-push to an existing setup.
Git needs Pixi on `PATH` to run them.
For Jujutsu changes, run `pixi run lint`, `pixi run check-rust`, and
`pixi run check-types` explicitly.

Use the `artifacts` environment to build a wheel on any supported platform:

```bash
pixi run --locked -e artifacts maturin build --release --locked --out dist -i python
```

Python changes take effect in the editable installation.
After changing Rust, rebuild the extension in the environment you use:

```bash
pixi reinstall --locked -e test wesl-py
```

Replace `test` with `gpu`, `testing`, or `dev` when working in those environments.

## Find the code

| Location | Contents |
| --- | --- |
| `python/wesl/` | Python API, type stubs, shader executor, and pytest plugin |
| `src/` | Rust bindings and shader instrumentation |
| `python/wesl/shaders/wgsl_test/` | Bundled upstream assertion shaders |
| `tests/` | Python, Rust, and shader tests |
| `examples/` | Graphics and compute examples, with tests in `tests/examples/` |
| `docs/` | API reference and shader testing guide |

See the [API reference](docs/api.md) for compiler behavior and
[shader testing guide](docs/testing.md) for the executor and pytest fixtures.

## Verify your change

Run tests for the behavior you change. For compilation:

```bash
pixi run -e test python -m pytest tests/test_compile.py -q
```

The `test` environment adds pytest without GPU dependencies.
Use `tests/test_check_syntax.py`, `tests/test_diagnostics.py`, or
`tests/test_sources.py` for syntax checks, diagnostics, or source loading.
The Rust regression test runs with
`pixi run -e test cargo test --locked --test upstream`.

GPU checks use additional environments:

- Generated WGSL: `pixi run -e gpu python -m pytest tests/test_compute.py -q`
- Shader executor and pytest plugin: `pixi run -e testing python -m pytest
  tests/test_testing.py tests/test_pytest_plugin.py tests/shaders -q`
- Oldest supported pytest series: `pixi run -e testing-oldest python -m pytest
  tests/test_pytest_plugin.py -q`

The `gpu` environment adds NumPy and wgpu-py.
The `testing` environment also includes the example dependencies and pytest plugins.
The `testing-oldest` environment checks pytest 8.2.x.
These tests accept hardware and software WebGPU adapters.
Each [example](examples/README.md) documents its own test command.
See the [testing examples](tests/examples/testing/README.md) for snapshot updates
and [viewer checks](#viewer-checks) for example UI changes.

WESL tests exercise SDF functions. Python tests verify execution and reports.
Assertions follow the upstream
[wgsl-test API](https://github.com/webgpu-tools/wesl-js/blob/main/packages/wgsl-test/API.md).
Execution uses wgpu-py and needs no Node.js.

For code changes, run the style, Rust, and type checks:

```bash
pixi run lint
pixi run check-rust
pixi run check-types
```

`lint` checks Python, Markdown, TOML, and GitHub configuration.
It does not change files.
It includes new files and respects `.gitignore`.
Its environment uses conda dependencies and needs no Rust or wesl-py installation.
Markdown checks skip macOS because conda-forge has no rumdl build for Apple Silicon.
Dependencies use version ranges. `pixi.lock` records resolved versions.
CI pins Pixi separately from the workspace minimum.
Validate new Pixi releases before updating all four setup steps.
Dependabot's seven-day cooldown covers Actions, not Pixi.
`check-rust` runs rustfmt and Clippy in `rust`.
It needs no wesl-py or GPU dependencies.
`check-types` runs ty, Pyrefly, Pyright, and native stubtest in `dev`.
It needs no GPU adapter.
Run individual checks with `pixi run -e dev <task>`:
`check-ty`, `check-pyrefly`, `check-pyright`, or `check-stubs`.
`check-stubs` rebuilds the native extension with
`pixi reinstall --locked -e dev wesl-py` before running stubtest.
Run `pixi run generate-stubs` after changing a native signature.
Maturin generates stubs from PyO3 metadata with the optional `stub-gen` feature.
`pixi run format` applies Ruff, rustfmt, Tombi, and automatic rumdl fixes.
Use `pixi run -e lint prek run --all-files` to exercise the commit hooks explicitly.
Use `pixi run -e lint prek run --stage pre-push --all-files` for the push hooks.
Rustfmt uses the Rust 2024 style.
`pyproject.toml` enables all rumdl rules.
Use sentence case for headings, 80 columns for prose, and 88 for code blocks.

Tombi reads `pyproject.toml`. Its general lint rules are errors.
Schema validation uses strict mode.
Checks fail on warnings, including schema deprecations.
Hooks check `.toml` files. Cargo formats `Cargo.lock`.
Actionlint enables all checks, including its ShellCheck and Pyflakes integrations.
Its [configuration](.github/actionlint.yaml) rejects undeclared `vars` references.
Zizmor uses the default `regular` persona in CI and hooks.
Use `--persona auditor` for manual security reviews.
The release workflow suppresses `self-repository` until Actionlint accepts
GitHub's `$/` syntax for reusable workflows.
CI supplies a GitHub token for online Zizmor audits.
Local audits run offline unless `GH_TOKEN`, `GITHUB_TOKEN`, or
`ZIZMOR_GITHUB_TOKEN` is set.
Hook commands and file filters live in [prek.toml](prek.toml).
Hooks use prek's `system` language with Pixi environments.
Formatters run in separate priority groups.
Read-only checks run concurrently at priority 10.
Ruff formats Python blocks before rumdl.
Pre-push runs rustfmt before Clippy and static type checks of source and stubs.
Stubtest runs at priority 20 to avoid overlapping its rebuild with these checks.
Rust changes also select stubtest.

Ruff checks Python files, type stubs, notebooks, and Python blocks in Markdown.
Cargo denies Clippy's `all` and `pedantic` groups plus selected restriction and
nursery lints.
See [Cargo.toml](Cargo.toml) and [clippy.toml](clippy.toml) for the rules and
complexity limits.

Run these additional checks when the change affects the corresponding area:

- Native threading: `pixi run -e test python -m pytest
  tests/test_threading.py
  tests/test_compile.py::test_concurrent_feature_state_isolation
  tests/test_diagnostics.py::test_concurrent_diagnostics_remain_independent -q`
  verifies concurrent compilation, diagnostics, and shader instrumentation.
  See [thread behavior](docs/api.md#threads).
- Rust dependencies: `pixi run check-dependencies` runs Machete against the binding
  manifest and Cargo-deny for licenses and RustSec advisories.

`pixi run test` runs all Rust, Python, and shader tests in `testing`.
Use targeted commands while working on a change.
For prose-only changes, verify links and commands in the affected documentation.

### Viewer checks

Linux CI selects Vulkan and uses Mesa's software adapter.
Viewer tests render offscreen:

```bash
pixi run -e testing python -m pytest \
  tests/examples/test_example_render.py tests/examples/test_sdf.py -q
```

After changes to pointer handling or widget layout, open the affected example.
Verify its controls before and after resizing the window.

## Edit shaders

Configure your editor to use the nearest `wesl.toml` as the wgsl-analyzer
project root.
The repository manifest covers all examples and tests.
The bundled `wgsl_test` library has its own manifest.
See [shader editing](docs/testing.md#shader-editing) for setup in other projects.

## Open a pull request

Describe the problem, the resulting behavior, and the checks you run.
Keep the change focused. Include a regression test when fixing a behavior defect.
Update the relevant guide or example when changing the public API.

The [CI workflow](.github/workflows/artifacts.yml) checks source, editable installs,
and Python 3.12 wheels on Linux, macOS, and Windows.
Linux also tests wheels on Python 3.13, 3.14, and 3.15.
CI checks repaired wheels with `check-wheel-contents`, Twine, and ABI checks.
`check-wheel-contents` is available in `artifacts`.
It requires the files from `python/wesl`, excluding local builds and bytecode.
W102 is disabled to allow compiled extensions and repaired libraries.
Installation checks verify native imports, type information, and bundled shaders.
The [release checklist](RELEASE_CHECKLIST.md) describes PyPI setup and publication.

## Maintenance

- Add GPU and example execution to macOS and Windows CI.
  Their Pixi environments resolve on all three platforms.
  GPU execution currently runs only on Linux CI with Mesa's Vulkan adapter.
  Verify suitable adapters and display support before extending these jobs.
- Enable rumdl on macOS when conda-forge supplies an arm64 build.
  The feedstock does not configure this target.
  [Issue #4](https://github.com/conda-forge/rumdl-feedstock/issues/4) tracks it.
- Keep the ImGui upper bound while PyPI wgpu 0.32.0 uses the removed
  `cmd_lists_count` attribute. Conda's [backend patch](https://github.com/conda-forge/wgpu-py-feedstock/blob/main/recipe/0001-Use-len-draw_data.cmd_lists-in-imgui-backend.patch)
  makes newer versions work. Verify the PyPI dependencies before changing the bound.
- Use the pinned upstream visitor for statements and expressions. Published
  WESL 0.5.0 omits plain `else` branches in [its visitor](https://github.com/webgpu-tools/wesl-rs/blob/63a3627ba31258565df177f3f553beed8ff45338/crates/wesl/src/pass/visit.rs).
  The pin includes the fix from [PR #307](https://github.com/webgpu-tools/wesl-rs/pull/307).
- Keep the compiler adapter for module transformations. Remove its workarounds
  as upstream resolves the [integration gaps](docs/upstream.md#compiler-driver-integration).
  Check the reproducers and removal criteria when updating the WESL pin.
- Review GPU resource and ImGui context cleanup for repeated viewer use.
  The SDF viewer has no explicit teardown. Its particle buffer remains usable
  after the canvas closes while the viewer remains referenced.
  The [wgpu renderer](https://github.com/pygfx/wgpu-py/blob/main/wgpu/utils/imgui/imgui_renderer.py)
  creates the ImGui context without a cleanup method.

### Pytest plugin

The repository manifest sets the shared shader root.
Directory fixtures keep example parameters local.
The root configuration uses importlib mode so test filenames can repeat.

Pytest controls parametrization and fixture setup, including autouse fixtures.
The plugin preserves collected items and their state, then adds WESL reporting.
The runner evaluates test conditions after fixture setup.
Tests cover the oldest supported and current pytest series.

`pytest_generate_tests` exposes shader callables during collection.
The collector then removes them to prevent shader names from becoming Python hooks.

The plugin returns [custom failure strings](https://docs.pytest.org/en/stable/example/nonpython.html)
through `repr_failure` to preserve locations in terminal, JUnit, and xdist reports.
Keep the regression tests.
The plugin leaves presentation to pytest and uses no private traceback classes.
Chained exceptions use the item's original `repr_failure` to retain their causes.
