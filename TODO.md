## CI
- [x] Why GIL not No-GIL/Freethreading? Did we not implement this?
- [x] CI Pins rust and * everything. either star all or pin all. Likely star all.

CI tests both regular Python and Python 3.15t. Build tools use `*` and a lockfile.

## Linting
- [x] Add ty and pyrefly and pyright to type checking optional dependencies for dev, contribution guide, ci
- [x] maybe restructure lib to avoid `ruff check python tests tools examples recipe` -> `ruff check python`
- [x] Review the organization of `tests/` and `examples/`.

Ruff checks the repository with `ruff check .`. All tests live under `tests/`.
One root pytest configuration collects the suite. Directory fixtures select shader roots.

## Freethreading
- [x] Implement python freethreading support whereever it would be helpful but maintain compatibility with GIL python


## Packaging / Dypendencies
- [x] Review pyproject.toml and pixi.toml for current packaging conventions. Set the minimum version of each dependency to exclude unsupported releases.
- [x] Make sure that the pixi.toml can run the tests in full so I can tell contributors to use pixi
- [x] Brige the rust and python gap here with convienent pixi tasks. pixi run test pixi run lint pixi run format. have them do both rust and python (object to this if you think its wrong)

## Shader tests

- [ ] Make floating-point assertions fail on nonfinite operands or tolerances. Check the exponent bits before scalar and vector comparisons. Add regressions for matching NaNs, matching infinities, infinity versus a finite value, and overflow from finite operands. Document that WGSL can produce an indeterminate finite result after overflow.
