# Testing and CI

ChemBlender release validation uses four layers. Passing an earlier layer does not replace a later one.

## 1. Repository Contracts

Use Blender's bundled Python 3.13; pytest is not required.

```powershell
$pythonBin = 'C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe'
& $pythonBin -m unittest discover -s tests -p 'test_*.py' -v
& $pythonBin -m compileall -q ChemBlender tests
```

Contracts cover manifest metadata and permissions, ignored dependencies, lifecycle wiring, package-install prohibition, package exclusions, changelog extraction, and CI pins.

## 2. Validate and Build

```powershell
$blenderBin = 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe'
& $pythonBin ChemBlender/scripts/validate_extension.py --source-path ChemBlender --blender $blenderBin
& $pythonBin ChemBlender/scripts/build_extension.py --python $pythonBin --blender $blenderBin
```

The built ZIP must contain the manifest, license, RDKit wheel, and two `.blend` libraries. It must not contain tests, development scripts, caches, or nested ZIP files.

## 3. Isolated Blender Install

```powershell
$package = (Get-Item 'ChemBlender\chemblender-2.2.0.zip').FullName
$env:BLENDER_USER_RESOURCES = (New-Item -ItemType Directory -Path '.agents\cache\blender-release-clean' -Force).FullName
& $blenderBin --background --factory-startup --python-exit-code 1 --python tests/blender_smoke.py -- $package
Remove-Item Env:BLENDER_USER_RESOURCES
```

This proves that an existing user extension or shared `.local` directory did not satisfy a missing dependency. The smoke test covers package contents, RDKit behavior, installed blend libraries, registration, repeated reload, and unregister.

## 4. Real Installation and GitHub Actions

Reinstall the same package into the real `user_default` repository from a fresh Blender process. Do not close an interactive Blender automatically; save work and close it before replacing loaded wheel DLLs.

GitHub Actions starts with the `native-core` job on `windows-latest`. It uses
only repository checkout and `actions/setup-python`, then runs the explicit
standard-library dependency-inventory, legacy-fixture, documentation, and
repository-contract suites, `compileall`, and `git diff --check`. It neither
downloads Blender or wheels nor installs runtime packages; Gemmi/RDKit coverage
therefore remains in the package job instead of being misreported as native
coverage.

The native checkout fetches full history. Its format check calls the
standard-library `tests/check_committed_format_range.py` helper, so the
workflow and local contract tests use the same event selection. A nonzero
40-hex pull-request base SHA or push `before` SHA must identify an exact local
commit; if it is absent locally, the helper explicitly fetches that SHA from
`origin` and fails closed if it remains unavailable. It never substitutes a
parent for a declared event base.

The Windows PowerShell workflow passes every helper value as
`--flag="$env:VAR"`. Keeping the option and its possibly empty value in one
native-command argument prevents PowerShell from dropping nullable GitHub
event values before `argparse` receives them.

An empty or all-zero push `before` (a new branch), and events without a base,
first use the merge base with the default branch. If that ref cannot be used,
the helper compares the complete committed tree from Git's empty tree rather
than silently checking only the last commit. Its final command is
`git diff --check <base> HEAD`, so trailing whitespace in an earlier committed
head cannot be hidden by a clean checkout. Deleted pushes skip `native-core`;
because `package` needs that job, it cannot build or upload an artifact.

The `package` job explicitly `needs: native-core`. It uses a temporary
`BLENDER_USER_RESOURCES`, downloads Blender and the approved RDKit/Gemmi wheels
from pinned sources, verifies their checksums, validates/builds the ZIP, and
runs the isolated cold-install lifecycle smoke. Before its only upload, it
generates canonical `wheel-inventory.json`, `wheel-license-copy-list.json` and
`artifact-size.json`, rechecks nested wheel hash/size/license evidence and the
versioned `.github/artifact-budgets.json`, then verifies the staged five-file
artifact in explicit `package-ci` mode. The budget has zero unexplained package
growth: a future baseline change must be reviewed with fresh package evidence.
Only this job uploads the tested ZIP, checksum and those small metadata files,
so its artifact is authoritative. Action
implementations are pinned to full commit SHAs and both jobs have read-only
repository access. Pull-request and `main` runs gate integration; the
successful run for the exact annotated tag is the authority for public Release
assets. A local equivalent run alone is not CI proof.

`optional-qc-core` is a separate read-only workflow for the optional scientific
backends. Its cclib and IOData jobs use isolated CPython 3.13 environments; its
GBasis job uses the supported CPython 3.12 and NumPy 1.26.4 environment. Each
job has one complete exact runtime lock under `.github/constraints/`: pip uses
it with `-c`, and the same file is passed to
`ChemBlender/scripts/run_required_integration.py`. These locks include every
direct and resolved transitive runtime distribution, excluding installer tools.
Each job initializes only its pinned submodule commit, checks every selected
fixture SHA-256 before loading tests, and invokes the runner with an explicit
module list. The runner checks every lock entry through `importlib.metadata`
and writes a canonical JSON summary containing required and actual
Python/package versions, fixture hashes, counts and test IDs. Only ordinary
successes may pass: a targeted skip, expected failure, unexpected success,
subtest failure/error, load error, no discovered tests, version/fixture mismatch
or ordinary failure/error fails that job. Unrelated optional tests are not in
these required module lists. The workflow uploads only the small JSON summaries,
never a submodule source archive.

`ChemBlender/scripts/verify_release_artifact.py` has an explicit metadata mode.
`package-ci` requires and recomputes the size report, wheel inventory and
license list against the ZIP; `release-assets` accepts only ZIP/checksum for a
published asset pair. Local and CI archive hashes may differ because ZIP
metadata is regenerated; the tag CI checksum is authoritative for the package
selected by the Release workflow.

Pillow is outside the 2.2.0 package while no extension code imports PIL or uses Pillow-dependent RDKit behavior. Any such feature must update the dependency decision, manifest, and CI together.

The manually dispatched `extension-release` workflow performs a read-only validation run by default. With `publish=true`, its environment-gated job re-verifies the same artifact, extracts the matching `CHANGELOG.md` entry, creates a draft with that body, compares Release asset digests, and publishes it. It does not rebuild or repeat Blender runtime testing. The complete procedure is maintained in [Branch and Release Workflow](branch-and-release.md).
