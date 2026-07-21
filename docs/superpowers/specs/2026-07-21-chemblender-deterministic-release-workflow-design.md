# Deterministic Extension Release Workflow Design

## Goal

Publish only the exact ChemBlender extension artifact produced and tested by the successful workflow run for an annotated release tag. Keep verification deterministic, publication explicitly authorized, and routine package CI read-only.

## Decision

Add `.github/workflows/extension-release.yml` with a manual `workflow_dispatch` trigger and two inputs:

| Input | Default | Purpose |
| --- | --- | --- |
| `tag` | none | Existing annotated `vMAJOR.MINOR.PATCH` tag to verify |
| `publish` | `false` | Run verification only, or publish after verification |

The workflow has two jobs:

1. `verify` uses `actions: read` and `contents: read`. It proves the tag, commit, successful package run, artifact, checksum, and ZIP contract.
2. `publish` runs only when `publish` is true, depends on `verify`, uses `contents: write`, and is bound to the `release` environment. It downloads and verifies the same artifact again, creates a draft Release, verifies uploaded asset digests, and then publishes it as the latest Release.

`workflow_dispatch` is the explicit release request. The `release` environment is the optional repository-settings approval gate; the workflow remains deterministic whether or not required reviewers are configured.

## Verification Contract

The workflow must fail before publication unless all conditions hold:

- the input matches `vMAJOR.MINOR.PATCH`;
- the remote ref is an annotated tag and its commit is in `origin/main` history;
- the tag version equals `ChemBlender/blender_manifest.toml`;
- the successful `extension-package` push run has the same tag name and exact commit SHA;
- the expected Actions artifact exists exactly once and is not expired;
- the artifact contains exactly the versioned extension ZIP and adjacent checksum record;
- the checksum matches the ZIP;
- the ZIP contains the manifest, license, declared RDKit wheel, and two `.blend` libraries, while excluding development-only paths and extra wheels;
- no GitHub Release already exists for the tag before publication;
- GitHub reports the expected SHA-256 digest for each uploaded Release asset.

Use Python's standard library for manifest, checksum, and ZIP validation. Keep that logic in one small script callable both locally and from Actions. Do not download Blender or rerun runtime smoke tests in the Release workflow: the exact tag package workflow already performed those expensive checks.

## Publication and Failure Behavior

The publish job generates release notes with GitHub's native release-note generation and uploads only the verified ZIP and checksum. It creates a draft first. Digest failure leaves a private draft for inspection; only a digest-clean draft is changed to a public latest Release.

A verification-only run performs no external write. A failed publish run never deletes or replaces an existing Release automatically. Maintainers inspect and remove an invalid draft before retrying. Published tags and binaries are immutable by policy; corrections use a new patch version.

## Tests

Extend the existing standard-library repository contracts before implementation. The tests require the trigger, inputs, job-level permissions, environment gate, exact-run selection, artifact re-verification, draft-first publication, digest check, and full action SHA pins. Add focused temporary-ZIP tests for the validator's success, checksum failure, and package-contract failure paths.

No new Python or GitHub Action dependency is introduced.
