# ChemBlender 2.2.0 Release Readiness Design

## Goal

Prepare the maintained fork for a reproducible ChemBlender 2.2.0 extension release: keep the repository focused, prove a clean install in Blender 5.1.2, and obtain a real green GitHub Actions run from a draft pull request.

## Confirmed Scope

- Continue on `feat/2.2.0-extension`, whose base is local `main` at `v2.1.1`.
- Keep `unittest`; do not add pytest while the existing standard-library runner covers the release contracts.
- Use Blender 5.1.2 on Windows x64 and CPython 3.13 for the first 2.2.0 package.
- Use Blender's bundled NumPy and Requests.
- Bundle the pinned RDKit 2026.3.3 Windows CPython 3.13 wheel through the manifest.
- Do not bundle Pillow while ChemBlender does not import PIL or use Pillow-dependent RDKit features. Revisit this decision before adding such a feature.
- Declare the actual `files` and `network` runtime permissions. Network access exists for remote molecular/scaffold data, not package installation.
- Never install packages during import, registration, or add-on enable.
- Keep local wheels, generated ZIP files, caches, and test profiles ignored and untracked.
- Push the approved release baseline and feature history, open a draft pull request to the maintained fork's `main`, and require a real GitHub Actions result.

## Repository Cleanup Boundary

Tracked project history, governance documents, the repository-local Blender skill, source, tests, and release documentation remain. Root and packaged copies of `LICENSE` both remain because GitHub and the extension archive need their own discoverable license.

Remove only confirmed redundancy:

- stale links to the completed `.agents/active/2.2.0-extension.md` task;
- generated caches and old ignored ZIP artifacts;
- development scripts from the built extension ZIP through manifest exclusions;
- duplicate local branch names only after equivalent durable refs are pushed and verified.

Do not delete executed specifications or plans: they provide the requested traceable development record.

## Release Test Architecture

### Repository contracts

The existing `tests/test_repository_contract.py` remains the dependency-free test entrypoint. It checks manifest metadata and permissions, wheel identity, ignored/generated-file policy, extension lifecycle wiring, runtime package-install prohibition, CI pins, and build exclusions.

### Package validation

Use Blender's native extension validator and builder. Inspect the generated ZIP with Python's `zipfile` module and require the manifest, license, RDKit wheel, and two `.blend` assets. Reject tests, caches, nested ZIPs, and development scripts.

### Clean Blender runtime

Run `tests/blender_smoke.py` in a background Blender process with a temporary `BLENDER_USER_EXTENSIONS` directory. The smoke test installs the built ZIP into `user_default` and verifies:

- module key `bl_ext.user_default.chemblender`;
- RDKit 2026.3.3 import plus representative `Chem` and `AllChem` operations;
- both installed `.blend` libraries and their expected node-group counts;
- registered object and scene properties;
- two disable/enable cycles and clean final unregister.

The isolated run prevents an existing user installation or shared extension `.local` directory from hiding missing dependencies.

### User installation

After the isolated run passes, reinstall the same ZIP into the real `user_default` repository. If the connected interactive Blender has loaded wheel DLLs or contains unsaved work, pause for the user to save and close Blender before replacing the package. Do not terminate an interactive Blender process automatically.

## CI Design

The Windows workflow performs the same sequence as local validation:

1. check out the exact commit with read-only repository permissions;
2. download the pinned RDKit wheel and verify SHA-256;
3. download Blender 5.1.2 and verify the official archive checksum;
4. run repository contracts;
5. validate, build, and audit the extension ZIP;
6. run the isolated Blender lifecycle smoke test;
7. upload the verified ZIP and its SHA-256 record.

GitHub-owned actions are pinned to reviewed full commit SHAs. The draft pull request into the maintained fork's `main` is the first authoritative CI run. A local equivalent run is evidence, but not a substitute for GitHub Actions.

## Git and Remote Order

Use one commit per logical phase: release policy and cleanup, test/runtime hardening, then CI hardening. After all local gates pass:

1. push `main` and annotated tag `v2.1.1`;
2. push `archive/extension-spike-20260707`;
3. push `feat/2.2.0-extension`;
4. open a draft pull request from the feature branch to `main`;
5. inspect the actual check logs and downloaded artifact;
6. fix only reproduced failures and rerun the same gates;
7. remove duplicate local branches after their replacement refs are verified;
8. request explicit confirmation before deleting the old remote snapshot branch or merging the draft pull request.

The redundant `release/2.1.1` branch is not pushed because `main` and `v2.1.1` preserve the same commit.

## Completion Criteria

The release-readiness goal is complete only when the repository is clean, local contracts and Blender gates pass from an isolated extension root, the real user installation is verified, the draft pull request exists, GitHub Actions is green, and the uploaded artifact matches the locally defined package contract. GitHub merge and public release publication remain separate user-approved actions.

The implementation plan under `docs/superpowers/plans/` is the live task authority. It may be corrected when runtime evidence invalidates an assumption; every material correction is committed with the work it governs.
