# Branch and Release Workflow

## Baselines

| Ref | Purpose |
| --- | --- |
| `origin/main` | Maintained ChemBlender releases |
| `upstream/main` | Original project reference |

The maintained fork may diverge for extension packaging and CI. This does not prevent later upstream PRs, but those PR branches must start from freshly fetched `upstream/main` and contain only the relevant code and tests.

## Branches

- `archive/*`: read-only experiment history.
- `release/*`: focused release preparation.
- `feat/*`: maintained downstream features.
- `upstream-pr/*`: clean upstream contribution branches.

## Canonical Release Model

ChemBlender uses **read-only package CI plus a manually dispatched, deterministic Release workflow**.

- `.github/workflows/extension-package.yml` runs for pull requests, pushes to `main`, and `v*` tags.
- The workflow downloads pinned Blender and RDKit inputs, verifies their checksums, runs repository contracts, builds the extension, exercises it in an isolated Blender profile, and uploads the tested ZIP plus its SHA-256 record.
- `.github/workflows/extension-package.yml` has `contents: read`; it never creates a GitHub Release.
- `.github/workflows/extension-release.yml` locates the successful exact-tag run, downloads and audits its artifact, and performs no write when `publish=false`.
- With `publish=true`, only the `publish` job receives `contents: write`. It creates a draft, verifies the uploaded asset digests, and then publishes the Release.
- Never rebuild between the successful tag run and publication. The GitHub Release assets must be byte-for-byte identical to the files downloaded from that run.

This is the preferred balance for the current Windows-only release line. A tag push alone cannot publish, routine CI remains least-privileged, and deterministic checks replace manual artifact transfer. Release timing is still a human decision; package selection and digest verification are not. No large language model is used.

GitHub recommends full commit SHA pins for immutable action code and supports SHA-256 validation when workflow artifacts are uploaded and downloaded. See [Secure use reference](https://docs.github.com/en/actions/reference/security/secure-use) and [Store and share data with workflow artifacts](https://docs.github.com/en/actions/tutorials/store-and-share-data).

## CI-to-Release Checks

The Release workflow verifies all of these conditions before publication:

| Check | Evidence |
| --- | --- | --- |
| Release identity | Input is an annotated `vMAJOR.MINOR.PATCH` tag in `origin/main`; tag version equals the manifest |
| Package provenance | Successful `extension-package` push run has the same tag name and exact commit SHA |
| Artifact availability | Exactly one expected, unexpired Actions artifact exists |
| Package integrity | Artifact has only the versioned ZIP and checksum; SHA-256 matches |
| Package contract | Manifest, license, declared wheel, and both `.blend` libraries exist; development paths and extra wheels do not |
| Publication safety | No Release already exists; draft asset digests equal the downloaded files before publication |

## Release Procedure

### 1. Prepare and verify `main`

Merge the focused feature or release branch into maintained `main`. Confirm that the worktree is clean, the manifest version is final, and the pull-request and `main` workflow runs are green. Run all local gates in [Testing and CI](testing-and-ci.md), including the isolated and real Blender installations.

```powershell
git switch main
git pull --ff-only origin main
git status --short --branch
git diff --check
```

Do not release directly from `archive/*` or a downstream branch. Do not treat a locally built ZIP as a substitute for GitHub Actions evidence.

### 2. Create and push one annotated tag

```powershell
$version = '2.2.0'
$tag = "v$version"

git tag -a $tag -m "Release $tag"
git show --no-patch --decorate $tag
git push origin $tag
```

Push only the intended tag; do not use `git push --follow-tags`. The tag workflow rejects a tag whose version does not equal `blender_manifest.toml`.

### 3. Run verification only

```powershell
$repo = 'psiQAQ/ChemBlender_2_x'
gh workflow run extension-release.yml --repo $repo `
  -f tag=$tag -f publish=false
gh run list --repo $repo --workflow extension-release.yml `
  --event workflow_dispatch --limit 5
```

This run is read-only. It selects the successful package run by exact tag commit, downloads its artifact, and runs `ChemBlender/scripts/verify_release_artifact.py`. Inspect and require a green result before requesting publication.

### 4. Dispatch publication

```powershell
gh workflow run extension-release.yml --repo $repo `
  -f tag=$tag -f publish=true
```

This is the explicit publication authorization. The workflow repeats artifact verification inside its `release` environment, creates a draft with GitHub-generated notes, compares both GitHub asset digests, and publishes only after they match. It then confirms that the tag is the latest public Release.

Repository administrators should configure required reviewers under **Settings → Environments → release** when a second approval is desired. Without that protection rule, the manual `publish=true` dispatch remains the sole human approval.

### 5. Record evidence

Record the tag commit, package run URL, verification and publication run URLs, artifact name, package SHA-256, and Release URL in the release completion evidence.

## Failure Rules

- If a local, pull-request, `main`, or tag gate fails, do not publish.
- Fix the issue on a branch, merge it into `main`, and create a new version/tag as appropriate; do not silently move a published tag.
- A digest or publication failure may leave a private draft. Inspect and remove it manually before retrying; the workflow never deletes Releases.
- Once users may have downloaded a Release, publish a patch release instead of replacing its tag or binaries.
- Actions artifacts expire; the durable public deliverables are the Release ZIP and checksum. GitHub documents artifact retention separately from repository Releases in [Downloading workflow artifacts](https://docs.github.com/actions/managing-workflow-runs/downloading-workflow-artifacts) and [About releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases).

## Current Version Boundary

- 2.1.1: final legacy add-on; asset compression only.
- 2.2.0: first published extension; source under `ChemBlender/`, offline RDKit wheel, extension-native install, and package CI.
