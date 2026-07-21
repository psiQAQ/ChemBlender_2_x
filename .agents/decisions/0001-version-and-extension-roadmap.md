# Decision 0001: Version and Extension Roadmap

## Context

Commit `78c2d8d` imported upstream ChemBlender 2.1.0 over the older repository. A later spike mixed extension packaging, namespace fixes, a tracked RDKit wheel, and compressed `.blend` files.

## Decision

1. Preserve `78c2d8d` as the 2.1.0 baseline.
2. Release 2.1.1 as a legacy add-on containing only asset compression and the version change.
3. Begin the extension migration at 2.2.0 from maintained `main@v2.1.1`.
4. Place the extension under `ChemBlender/` and keep the repository root as the development workspace.
5. Download the pinned RDKit wheel locally or in CI; do not track wheel binaries.
6. Keep `origin/main` as the maintained downstream line and `upstream/main` as the upstream reference.

## Consequences

- Users receive a small, low-risk 2.1.1 legacy update before the packaging transition.
- 2.2.0 can make extension-only namespace, lifecycle, dependency, directory, documentation, and CI changes coherently.
- Future upstream PRs must start from live upstream history and cannot directly reuse the downstream feature branch.
- Local builds require an explicit wheel download before validation/build.

## Rejected Alternative

Do not publish the mixed extension spike as 2.1.1. It changes installation and dependency behavior while claiming to be a small legacy maintenance release.
