# Release checklist

Release support is prepared for later use.
A push to `main` runs the artifact checks and does not publish to PyPI.
Publication requires a manual run of `release.yml` from a version tag.
Making the repository public does not start publication.

- [x] Remove private imports from upstream dependencies.
- [x] Consolidate tests around binding behavior.
- [x] Simplify the README and maintenance documentation.
- [x] Prepare installation instructions for published packages.
- [x] Prepare a manual release workflow that publishes tested artifacts.
- [ ] Make the repository public and complete the artifact workflow.
- [ ] Configure the PyPI publisher and GitHub environment.
- [ ] Publish the first release and verify installation from PyPI.
- [ ] Remove the pending-release notes from the README and testing guide.

## After making the repository public

1. Commit and push the documentation and prepared workflow changes to `main`
   when ready.
2. Open [Actions > Artifacts](https://github.com/claydugo/wesl-py/actions/workflows/artifacts.yml).
   Wait for the run on that commit to pass all jobs.
   If the changes are already on `main`, use **Run workflow** and select `main`.
   If GitHub still rejects jobs because of billing, resolve the account restriction
   before proceeding.

Continue to use the checkout installation instructions.
The repository can remain in this state until publication is wanted.

## Optional publication setup

Complete the steps below only when ready to publish to PyPI.
They are not required to push changes or make the repository public.

### Configure GitHub once

Open the repository's
[environment settings](https://github.com/claydugo/wesl-py/settings/environments).

1. Click **New environment**, enter `pypi`, and click **Configure environment**.
2. Under **Deployment branches and tags**, choose **Selected branches and tags**.
3. Click **Add deployment branch or tag rule**.
4. Set **Ref type** to **Tag**, enter `v*`, and click **Add rule**.

The publish job uses this environment.
See the [GitHub environment guide](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).

### Configure PyPI once

In the PyPI account's [publishing settings](https://pypi.org/manage/account/publishing/),
find **Add a new pending publisher**, select **GitHub**, and enter these values:

| Field | Value |
| --- | --- |
| PyPI project name | `wesl-py` |
| Owner | `claydugo` |
| Repository | `wesl-py` |
| Workflow filename | `release.yml` |
| Environment | `pypi` |

Click **Add** to save the publisher.
Use `release.yml` as the filename, without `.github/workflows/`.
The first upload creates the PyPI project.
A pending publisher does not reserve the package name.
Trusted Publishing uses GitHub's identity token and needs no PyPI API token.
See the [PyPI setup guide](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).

### Publish a version

1. Set the version in `Cargo.toml` and update `Cargo.lock`.
   Maturin uses this version for the Python distribution.
   The current version is `0.1.0`. Keep it for the first release.
2. Commit the release changes to `main` and complete the artifact workflow.
   The release workflow must also exist on the default branch before dispatch.
   Skip this step if that commit already passed the checks above.
3. Create a tag on that tested commit and push the tag to GitHub.
   The tag must match the package version: `v0.1.0` for the first release.
4. From the repository directory, start the release workflow from that tag:

   ```bash
   gh workflow run release.yml --ref v0.1.0
   gh run watch
   ```

   Select the **Release** run when `gh run watch` prompts.
   This workflow publishes to PyPI when its **Publish to PyPI** job runs.

The workflow rejects branches and tags that do not match the package version.
It runs the existing source, wheel, GPU, and example checks for the tagged commit.
It uploads the tested source distribution and wheels to PyPI after all checks pass.
The publish job downloads artifacts from that same run and does not rebuild them.
Ordinary pushes, pull requests, and tag creation do not publish a package.

After publication, verify the base package and `testing` extra in fresh environments.
Check native imports, bundled assertions, and pytest collection outside the checkout.
Confirm that [the PyPI project](https://pypi.org/project/wesl-py/) shows the release.
Remove the pending-release notes after the first successful publication.
