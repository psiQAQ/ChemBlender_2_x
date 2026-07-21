# Branch Architecture

Dynamic branch tips must be checked live. This document records stable roles and lifecycle changes.

## Long-lived Baselines

| Ref | Role | Allowed content |
| --- | --- | --- |
| `origin/main` | Maintained ChemBlender release line | Downstream releases, extension packaging, governance, and CI |
| `upstream/main` | Upstream reference | Upstream project history only |

## Branch Roles

| Pattern | Role | Merge policy |
| --- | --- | --- |
| `archive/*` | Immutable experiments and rejected/mixed history | Never used as a release base |
| `release/*` | Focused release preparation | Integrate into maintained `main` after verification |
| `feat/*` | Downstream maintained feature work | PR or merge into maintained `main` |
| `upstream-pr/*` | Minimal upstream contribution | Start from freshly fetched `upstream/main`; exclude downstream-only files |

## Lifecycle Rules

- Fetch and inspect live refs before creating a formal upstream branch.
- Investigation history may contain diagnostics; final upstream PR history contains only required code and tests.
- Record branch creation, role changes, integration, archival, renaming, and deletion in the same development phase.
- Do not delete local or remote branches without explicit authorization and a verified retained evidence path.

## Rebuild and Integration Record

- `archive/extension-spike-20260707` preserves the mixed Blender extension experiment and planning records.
- Annotated `v2.1.1` preserves the final legacy add-on at `2b72abf`.
- `feat/2.2.0-extension` started from `main@v2.1.1` and remains available for review provenance.
- PR #1 merged the verified extension history into maintained `main` as merge commit `8deeea1`.
- `archive/extension-spike-20260707` and the old remote snapshot remain separate retained evidence; neither is a release base.
