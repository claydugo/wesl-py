# Publication checklist

Publish to GitHub, then PyPI, then conda-forge.
See [CONTRIBUTING.md](CONTRIBUTING.md) for implemented checks and the release procedure.
See [ROADMAP.md](ROADMAP.md) for compiler upgrades and future integrations.

## Release verification

- [ ] Run the artifact workflow on the release revision. Require all platform jobs and the compute job to pass. The installed-wheel tests cover the documented upstream compiler defects.
- [ ] Resolve the Windows Python 3.15 `abi3t` import failure. Conda-forge's regular 3.15.0rc2 build omits `python3t.dll`. Keep the failing check until the runtime supports this ABI. [PyO3 DLL requirements](https://pyo3.rs/v0.29.2/faq#im-trying-to-call-python-from-rust-but-i-get-status_dll_not_found-or-status_entrypoint_not_found)
- [ ] Run smoke tests on the minimum supported OS runtimes without relying on conda's shared libraries.
- [ ] Review the README on TestPyPI. `twine check` verifies distribution metadata but does not check Markdown link targets.

## PyPI publication

- [ ] Add and review publication automation separately. Upload tested artifacts without rebuilding. Verify the required platform and ABI combinations. Compare existing file hashes before resuming a partial upload.
- [ ] Set up the PyPI and TestPyPI accounts with verified email addresses and two-factor authentication. Store the recovery codes. [PyPI account requirements](https://pypi.org/help/#twofa)
- [ ] Configure a pending Trusted Publisher for `wesl-py` on PyPI and a separate publisher on TestPyPI. Bind each to the GitHub repository and the chosen publishing workflow and environment. A pending publisher does not reserve the package name. [First publication with OIDC](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
- [ ] Rehearse on TestPyPI before the first PyPI release. Use Trusted Publishing with attestations. [PyPI publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/), [Automatic attestations](https://docs.pypi.org/attestations/producing-attestations/)
- [ ] Publish the verified artifacts and attach the same files to the GitHub release. Compare published file hashes with the tested artifacts. Verify installation and compilation in a fresh Pixi environment. Update the README installation instructions after publication.

## conda-forge submission

- [ ] Replace the recipe's checkout source with the published PyPI sdist URL and SHA256. [Submission requirements](https://conda-forge.org/docs/maintainer/adding_pkgs/)
- [ ] Verify the conda package on each intended platform and supported Python version. The recipe builds the regular CPython ABI3 extension. Free-threaded conda packages remain outside this recipe's scope. [conda-forge ABI3 guidance](https://conda-forge.org/docs/maintainer/knowledge_base/#packages-with-abi3-extensions), [Rattler ABI3 recipe](https://rattler-build.prefix.dev/latest/tutorials/python/#an-abi3-compatible-package)
- [ ] Submit the recipe to `conda-forge/staged-recipes` and resolve its checks before feedstock creation. [Staged recipe process](https://conda-forge.org/docs/maintainer/adding_pkgs/#step-by-step-instructions)
