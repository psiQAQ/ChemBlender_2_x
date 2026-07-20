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

## Release Order

1. Verify the feature/release branch locally.
2. Integrate into maintained local `main`.
3. Verify version metadata, package contents, install behavior, and a clean worktree.
4. Create the local annotated tag.
5. Request explicit approval before pushing branches/tags or creating a GitHub release.

## Current Version Boundary

- 2.1.1: final legacy add-on; asset compression only.
- 2.2.0: first extension; source under `ChemBlender/`, offline RDKit wheel, extension-native install, and package CI.
