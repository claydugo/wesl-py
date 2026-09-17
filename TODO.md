## CI
- [ ] Why GIL not No-GIL/Freethreading? Did we not implement this?
- [ ] CI Pins rust and * everything. either star all or pin all. Likely star all.

## Linting
- [ ] Add ty and pyrefly and pyright to type checking optional dependencies for dev, contribution guide, ci
- [ ] maybe restructure lib to avoid `ruff check python tests tools examples recipe` -> `ruff check python`
- [ ] like above tests/examples/ current organization is rough

## Freethreading
- [ ] Implement python freethreading support whereever it would be helpful but maintain compatibility with GIL python


## Packaging / Dypendencies
- [ ] Bring pyproject.toml and pixi.toml to 2026 best practices with minimum bounds ect
- [ ] Make sure that the pixi.toml can run the tests in full so I can tell contributors to use pixi
- [ ] Brige the rust and python gap here with convienent pixi tasks. pixi run test pixi run lint pixi run format. have them do both rust and python (object to this if you think its wrong)
