   Area                    What changes                                 Assessment
  ━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Diagnostics             An undefined name in an imported module      Must fix before release. This breaks an
                           loses its module identity and gets the       existing guarantee.
                           root shader’s source. Its byte span then
                           points into the wrong text.
  ──────────────────────  ───────────────────────────────────────────  ────────────────────────────────────────────
   Package visibility      Cross-package imports now require public     Manageable source adaptation. I verified
                           declarations. Existing external-library      that exporting the required assertion
                           fixtures and the bundled wgsl-test           declarations lets them compile and execute
                           shaders fail.                                on the GPU.
  ──────────────────────  ───────────────────────────────────────────  ────────────────────────────────────────────
   Test instrumentation    Resolver::resolve_module disappears. Our     Needs a deliberate port. The new
                           runner uses it to modify the AST while       CompilerDriver provides hooks for this,
                           retaining source locations.                  but conditional tests and diagnostics need
                                                                        focused verification.

  Visibility is an intentional upstream language change (https://github.com/webgpu-tools/wesl-rs/pull/279). The
  instrumentation change comes from the compiler frontend refactor
  (https://github.com/webgpu-tools/wesl-rs/pull/217).

  The remaining work is more routine:

  - Adapt native calls, source maps, and compilation results to the new API.
  - Remove lazy; upstream removed eager import resolution.
  - Map the renamed options, including keep_main and mangle_main. Upstream changes do not automatically require
    identical Python API changes.

  - Update expectations for keep: missing or conditionally disabled declarations now raise errors. Previously they
    produced empty output.

  - Refresh Cargo dependencies, compiler metadata, and license records.

  Lowering remains a separate release concern. I reconfirmed that 0.5 loses explicit constant types and emits
  unresolved forward references with lower=True. imports=False also still resolves imports. Those defects already
  exist in the exposed functionality; upgrading does not resolve them.

  On the patch question: the diagnostic defect occurs where upstream validates a module without attaching its
  source context. That needs correction upstream or in a custom compilation driver. A compiler fork is not an
  inherent requirement. I have identified the failure path, but have not verified a complete fix.

  The isolated port already builds with our existing toolchain. Six targeted checks passed for concurrent
  compilation, file resolution, unused imports, and mapping inputs. The adapted assertion shaders also executed
  successfully. Windows, macOS, and free-threaded builds still need verification.

  I would gate the upgrade on correct imported diagnostics and the complete @test path. Package visibility is the
  main additional compatibility change to account for upfront.
