# Allow one project description to define multiple local WESL packages

Status: Do not file. The investigation below assumes that our examples and tests
need separate package roots. They do not. A temporary copy uses one repository
root with `root = "."`, plus the existing `wgsl_test` library manifest.
After updating imports, 50 entry-point shader compilations and 27 native shader
test compilations pass across two feature configurations. One conditional test
is disabled. These checks verify compilation, not GPU execution or editor behavior.
Consolidating the repository configuration addresses our manifest duplication
without upstream changes. The original draft follows for reference.

Draft for [wgsl-analyzer](https://github.com/wgsl-analyzer/wgsl-analyzer/issues/new).

## What problem does this solve or what need does it fill?

I maintain [wesl-py](https://github.com/claydugo/wesl-py), a Python binding for WESL.
The repository contains application shaders, shader tests, a standalone testing
example, and a shared assertion library. These use different package roots.
Python can configure roots and named dependencies directly. For editor support,
we maintain separate `wesl.toml` files and repeat shared dependency declarations.

Some of our manifests are avoidable through local cleanup. However, preserving
the remaining package roots still requires several manifests.
I would like to describe these local packages in one place.

The current behavior follows the [manifest specification](https://wesl-lang.dev/spec/WeslToml).
This is a feature request for editor configuration.

## Small reproduction

Create this directory structure:

```text
project/
  wesl.toml
  shaders/
    main.wesl
  library/
    package.wesl
```

`wesl.toml`:

```toml
edition = "2026_pre"
root = "shaders"

[dependencies]
helper = { path = "library" }
```

`shaders/main.wesl`:

```wesl
import helper::value;

@compute @workgroup_size(1)
fn main() {
    let result = value();
}
```

`library/package.wesl`:

```wesl
public fn value() -> u32 {
    return 7u;
}
```

Open `shaders/main.wesl` with wgsl-analyzer. Project discovery reports:

```text
Project discovery failed: Package helper has an invalid path.
```

Adding `library/wesl.toml` clears the discovery error:

```toml
edition = "2026_pre"
root = "."
```

I reproduce this through LSP with `wgsl-analyzer 0.12.474-standalone` on Linux.
The [loader at 3254f08](https://github.com/wgsl-analyzer/wgsl-analyzer/blob/3254f083b3c0adc8fd0e87681d6ceca7ae721ffd/crates/wgsl-analyzer/src/discover.rs)
still requires a manifest in each path dependency directory.

## What solution would you like?

Support one project description that defines multiple local packages.
Each package needs its own edition, root directory, and named dependencies.
Tools could generate this description from their existing configuration.

The description should preserve each package's `package::` meaning and dependency
scope. Shared libraries should retain one identity when several packages use them.
I have no preference for the file format.

Is there an existing configuration that supports this?
The loader recognizes `wesl-project.json`, but currently rejects it with
`project json not supported`.

## What alternative(s) have you considered?

- Separate manifests work, but repeat configuration across the repository.
- One common root works if we change package boundaries and rewrite imports.
  It does not preserve the existing package layout.
- `include` and `exclude` select files within a root. They do not define additional
  package roots or dependency scopes. Their implementation is tracked in
  [#993](https://github.com/wgsl-analyzer/wgsl-analyzer/issues/993).
- `[package.metadata.wgsl-analyzer]` embeds one manifest in `Cargo.toml`.
  It does not provide a central description of several Python shader packages.

## Additional context

[#976](https://github.com/wgsl-analyzer/wgsl-analyzer/issues/976) tracks dependency
loading. This request concerns the description of local packages that the host
application already knows how to resolve.
