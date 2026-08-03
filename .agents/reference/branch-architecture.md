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
- The current 2.3.0 required-check contexts and branch-protection recommendation
  are documented in [2.3.0 Required Checks](../../docs/development/2.3.0-required-checks.md).
  They are not applied GitHub settings; an authorized administrator operation is
  required to change branch protection.

## Rebuild and Integration Record

- `archive/extension-spike-20260707` preserves the mixed Blender extension experiment and planning records.
- Annotated `v2.1.1` preserves the final legacy add-on at `2b72abf`.
- PR #1 merged the verified extension history into maintained `main` as merge commit `8deeea1`.
- Annotated `v2.2.0` preserves the first extension release at `cdc7236`; the matching GitHub Release publishes only the tested ZIP and checksum.
- Annotated `v2.3.0` and `v2.4.0` preserve their published release trees; merged feature and release branches are not required for release recovery.
- `archive/extension-spike-20260707` and the remote snapshot remain separate retained evidence; neither is a release base.

## Post-release Retention

- Merged `feat/*`, `release/*`, `docs/*` and `codex/*` refs may be removed after their exact heads are verified as retained by `origin/main` and their PR or Release evidence remains available.
- Prepared non-ancestor refs require patch, file and evidence equivalence before deletion.
- Removing a branch never authorizes moving or recreating an annotated tag or public Release.
- The ordinary Git history and `.agents/completed/` records, rather than redundant merged refs, are the durable development record.
