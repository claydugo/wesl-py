# Contributing

Bug reports, documentation fixes, examples, and code contributions are welcome.
If you want to try wesl-py, start with the [README](README.md) and
[examples](examples/README.md).

## Report a problem or suggest a change

Open an [issue](https://github.com/claydugo/wesl-py/issues) with a small example,
what you expect, and what happens instead.
For a bug, include the error output, your Python and wesl-py versions, and your
OS.
For a GPU failure, also include the adapter and backend.

Questions about unclear documentation are useful reports too.
For a larger change, an issue is a good place to discuss the approach first.

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

The pre-commit hook checks staged files before each Git commit.
File formatters receive only the selected filenames. Rustfmt checks the crate.
Changes to shared configuration trigger a read-only repository check.
It applies formatting fixes. Review and stage these fixes before trying again.
The pre-push hook runs Rust and Python type checks for relevant changes.
It includes deleted files when selecting checks. Documentation changes skip them.
The type check rebuilds the native extension before checking its stubs.
Install the hooks once per checkout. Run the command again to add the pre-push hook
to an existing setup. Git does not copy installed hooks when cloning.
Pixi must be on `PATH` when Git runs the hook.
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
The default environment also contains the editable extension.
The `freethreading` environment has a separate, non-editable installation.
Reinstall it after changing either Python or Rust code before testing Python 3.15t.

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

Run the tests that cover the behavior you change.
For a compiler change, for example:

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
It does not require the first patch release in that series.
These tests accept hardware and software WebGPU adapters.
Each [example](examples/README.md) documents its own test command.
See the [testing examples](tests/examples/testing/README.md) for snapshot updates
and [viewer checks](#viewer-checks) for example UI changes.

The WESL tests exercise the SDF example's production functions.
The Python tests verify the executor and its failure reports.
The assertion syntax follows the upstream
[wgsl-test API](https://github.com/webgpu-tools/wesl-js/blob/main/packages/wgsl-test/API.md).
Execution uses wgpu-py. It does not require Node.js or the JavaScript test runner.

For code changes, run the style, Rust, and type checks:

```bash
pixi run lint
pixi run check-rust
pixi run check-types
```

`lint` checks Python, Markdown, TOML, and GitHub configuration.
It does not change files.
It checks new files too. Tools respect `.gitignore` during file discovery.
The `lint` environment contains no Rust toolchain or wesl-py installation.
Pyflakes supports actionlint's Python checks.
On macOS arm64, Pixi installs rumdl from PyPI because conda-forge has no build.
The other platforms use conda-forge.
Dependency requirements use version ranges. `pixi.lock` records resolved versions.
CI uses a fixed Pixi bootstrap version. The workspace declares its minimum version.
This CI bootstrap is an exception to the package version policy.
Update all four setup steps together after validating a new Pixi release.
Dependabot's seven-day cooldown covers Action updates, not this bootstrap version.
`check-rust` runs rustfmt and Clippy in the separate `rust` environment.
Rust checks do not install the Python package or GPU dependencies.
`check-types` runs ty, Pyrefly, Pyright, and native stubtest in `dev`.
This environment includes wgpu so the type checkers can inspect its API.
Type checks do not request a GPU adapter.
The task rebuilds the native extension with
`pixi reinstall --locked -e dev wesl-py` before running the checks.
The type checkers check the Python API. Stubtest checks the compiled extension.
Run `pixi run generate-stubs` after changing a native signature.
Maturin generates stubs from PyO3's metadata with the optional `stub-gen` feature.
Normal builds do not include the stub generator.
`pixi run format` applies Ruff, rustfmt, Tombi, and automatic rumdl fixes.
It succeeds after applying fixes unless a tool reports an unresolved issue.
Use `pixi run -e lint prek run --all-files` to exercise the commit hooks explicitly.
Use `pixi run -e lint prek run --stage pre-push --all-files` for the push hooks.
Rustfmt uses the Rust 2024 style.
rumdl enables all rules, including opt-in rules, and respects `.gitignore`.
Its configuration lives in `pyproject.toml`. Headings use sentence case.
Code blocks allow 88 columns to match Ruff. Prose uses 80 columns.

Tombi uses the project configuration in `pyproject.toml`.
All three general lint rules are errors. Schema validation uses strict mode.
Tombi checks also fail on warnings, including schema deprecations.
Its hooks check `.toml` files. Cargo owns the generated `Cargo.lock` format.
Actionlint enables all checks, including its ShellCheck and Pyflakes integrations.
Its [configuration](.github/actionlint.yaml) rejects undeclared `vars` references.
Zizmor uses the `auditor` persona without suppressions.
CI provides a GitHub token so Zizmor can also run online audits.
Local runs use offline audits unless `GH_TOKEN`, `GITHUB_TOKEN`, or
`ZIZMOR_GITHUB_TOKEN` is set.
Hook commands and file filters live in [prek.toml](prek.toml).
Pixi supplies their tools and locks their versions in `pixi.lock`.
The hooks use prek's `system` language because Pixi manages the environments.
Hooks run in configuration order. Ruff formats Python blocks before rumdl runs.

Ruff checks Python files, type stubs, notebooks, and Python blocks in Markdown.
Cargo denies Clippy's `all` and `pedantic` groups plus selected restriction and
nursery lints.
See [Cargo.toml](Cargo.toml) and [clippy.toml](clippy.toml) for the rules and
complexity limits.
The binding uses `expect` attributes with reasons for its argument count and length.

Run these additional checks when the change affects the corresponding area:

- Native threading: `pixi run test-freethreading` verifies import without the GIL,
  concurrent compilation, diagnostics, and shader instrumentation on Python 3.15t.
  See [thread behavior](docs/api.md#threads).
- Rust dependencies: `pixi run check-dependencies` runs Machete against the binding
  manifest and Cargo-deny for licenses and RustSec advisories.

`pixi run test` runs all Rust tests and one pytest session over `tests/`, including
examples, shader tests, and snapshots. It selects the `testing` environment.
Use the targeted commands above while working on a change.
For prose-only changes, verify links and commands in the affected documentation.

### Viewer checks

GPU tests require a WebGPU adapter. Hardware and software adapters both work.
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

The [CI workflow](.github/workflows/artifacts.yml) runs development checks and
verifies built packages.
Source checks, editable installations, and free-threaded source builds run on
Linux, macOS, and Windows.
It tests Python 3.12 wheels on Linux, macOS, and Windows.
Linux also tests those wheels on Python 3.13, 3.14, and 3.15.
The free-threaded wheel runs on Linux with Python 3.15 and 3.15t.
The `artifacts` environment includes `check-wheel-contents`.
CI runs it on every wheel after platform repairs, alongside Twine and ABI checks.
Its project configuration requires the files from `python/wesl` in each wheel.
It excludes local extension builds and bytecode from that source comparison.
W102 is disabled because wheels add compiled extensions and repaired libraries.
Installation checks verify native imports, type information, and bundled shaders.

## Maintenance

- Add GPU and example execution to macOS and Windows CI.
  Their Pixi environments resolve on all three platforms.
  GPU execution currently runs only on Linux CI with Mesa's Vulkan adapter.
  Verify suitable adapters and display support before extending these jobs.
- Replace the macOS rumdl PyPI dependency when conda-forge supplies an arm64 build.
- Keep the ImGui upper bound while PyPI wgpu 0.32.0 uses the removed
  `cmd_lists_count` attribute. Conda's [backend patch](https://github.com/conda-forge/wgpu-py-feedstock/blob/main/recipe/0001-Use-len-draw_data.cmd_lists-in-imgui-backend.patch)
  makes newer versions work. Verify the PyPI dependencies before changing the bound.
- Use the pinned upstream visitor for statements and expressions. Published
  WESL 0.5.0 omits plain `else` branches in [its visitor](https://github.com/webgpu-tools/wesl-rs/blob/63a3627ba31258565df177f3f553beed8ff45338/crates/wesl/src/pass/visit.rs).
  The pin includes the fix from [PR #307](https://github.com/webgpu-tools/wesl-rs/pull/307).
- Keep the compiler adapter until upstream supports module transformations and
  resolves the [integration gaps](docs/upstream.md#compiler-driver-integration).
  Check the reproducers and removal criteria when updating the WESL pin.
- Track the [lost initializer](docs/upstream.md#lowering-drops-side-effects-in-a-for-initializer)
  when updating WESL. Both option classes default lowering to `False`.
  Shader tests have a partial workaround. Ordinary compilation remains affected.
  Verify the upstream fix before removing the local transformation.
- Review GPU resource and ImGui context cleanup for repeated viewer use.
  The SDF viewer has no explicit teardown. Its particle buffer remains usable
  after the canvas closes while the viewer remains referenced.
  The [wgpu renderer](https://github.com/pygfx/wgpu-py/blob/main/wgpu/utils/imgui/imgui_renderer.py)
  creates the ImGui context without a cleanup method.

### Pytest plugin

The repository manifest sets the shared shader root.
Directory fixtures keep example parameters local.
The root configuration uses importlib mode so test filenames can repeat.

The pytest plugin delegates parametrization to pytest's collection hook.
It keeps each collected item and its plugin state.
It attaches WESL reporting methods to the item.
Pytest controls fixture setup, including autouse fixtures.
The runner checks conditional tests after fixture setup.
The plugin tests cover the oldest supported and current pytest series.

The `pytest_generate_tests` hook exposes each shader callable during collection.
The collector then removes it from the synthetic module.
This prevents shader names from becoming Python hooks during subsequent collection.

The plugin returns [custom failure strings](https://docs.pytest.org/en/stable/example/nonpython.html)
through `repr_failure`. These strings preserve shader locations in terminal,
JUnit, and xdist reports. Keep the regression tests for these reports.
Pytest controls presentation. The plugin does not use private traceback classes.
Chained exceptions use the item's original `repr_failure` to retain their causes.
