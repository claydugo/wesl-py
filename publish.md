# Publication checklist

Publish to GitHub, then PyPI.
Submit the published sdist separately through [conda-forge/staged-recipes](https://conda-forge.org/docs/maintainer/adding_pkgs/#step-by-step-instructions).
See [CONTRIBUTING.md](CONTRIBUTING.md) for implemented checks.
See [ROADMAP.md](ROADMAP.md) for unresolved defects and deferred features.

## Release verification

- [ ] Update the Cargo version and [release notes](CHANGELOG.md). Record WESL upgrades, WGSL output changes, and diagnostic changes. Refresh dependency notices when needed.
- [ ] Run the artifact workflow on the release revision. Require all build jobs, wheel installation jobs, and compute jobs to pass. The Python regression tests cover the documented upstream compiler defects.
- [ ] Resolve the [Windows expression regression](ROADMAP.md#before-release). Its test must pass in every required wheel-test job.
- [ ] Review one sdist and six wheels. Verify both ABI families for each platform in the [support table](CONTRIBUTING.md#support).
- [ ] Run smoke tests on the minimum supported OS runtimes without relying on conda's shared libraries.
- [ ] Review the README on TestPyPI. `twine check` verifies distribution metadata but does not check Markdown link targets.

## PyPI publication

- [ ] Add and review publication automation separately. Upload tested artifacts without rebuilding. Verify the required platform and ABI combinations. Compare existing file hashes before resuming a partial upload.
- [ ] Set up the PyPI and TestPyPI accounts with verified email addresses and two-factor authentication. Store the recovery codes. [PyPI account requirements](https://pypi.org/help/#twofa)
- [ ] Configure a pending Trusted Publisher for `wesl-py` on PyPI and a separate publisher on TestPyPI. Bind each to the GitHub repository and the chosen publishing workflow and environment. A pending publisher does not reserve the package name. [First publication with OIDC](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
- [ ] Rehearse on TestPyPI before the first PyPI release. Use Trusted Publishing with attestations. [PyPI publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/), [Automatic attestations](https://docs.pypi.org/attestations/producing-attestations/)
- [ ] Create the matching version tag and GitHub release. Publish the verified artifacts without rebuilding. Attach the same files to the GitHub release. Compare published file hashes with the tested artifacts. Verify installation, compilation, and syntax checks in a fresh uv environment. Update the README installation instructions after publication.

For a partial upload, retain the original artifacts. Compare hashes of files
already on PyPI before uploading the missing files. For a broken release,
yank it with a reason and publish a corrected version. Never reuse its version.
See [PyPI's upload rules](https://docs.pypi.org/api/upload/) and
[yanking guidance](https://docs.pypi.org/project-management/yanking/).
