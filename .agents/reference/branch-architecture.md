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
| `archive/<date>/*` annotated tags | Retired branch tips, including experiments and rejected/mixed history | Immutable recovery refs; experiments are never used as a release base |
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

## Single-main Retention Policy (2026-09-08)

The user authorized consolidation of local and origin branches into one permanent main branch. Feature, fix and release branches are temporary. Before removing a branch, retain its exact tip with an annotated archive/<date>/<branch> tag and verify the tag commit. Push retained tags before deleting origin refs. Never move existing archive or version tags. upstream/main remains a read-only reference to the separate upstream repository.

main was fast-forwarded from 76c7cbc to 7def513, preserving all 40 commits of the unit-repair and experience-review branch. The following original tips are retained; two historical experiments are archive-only, not merged back into the supported extension tree.

| Original branch | Original tip | Archive tag | Disposition |
| --- | --- | --- | --- |
| `archive/extension-spike-20260707` | `24520d991ba17c81db93afa888809c27574a3875` | `archive/2026-09-08/extension-spike-20260707` | archive-only |
| `codex/user-workflow-experience-gate` | `3e1d02e046851c6c89a81ac8dce42b435bb25509` | `archive/2026-09-08/codex/user-workflow-experience-gate` | merged |
| `feat/qc-input-readers` | `76c7cbc8e7bbadfe578ffb95380b025bb7762856` | `archive/2026-09-08/feat/qc-input-readers` | merged |
| `fix/quantum-input-units-experience-review` | `7def5132fc32f4dda7678e6f89e3a7d3c9a16c61` | `archive/2026-09-08/fix/quantum-input-units-experience-review` | merged |
| `codex/2.4.0-task4-scope-discovery` | `d1ff05b82d1d7566c9f34c99c13e81a1ef59e234` | `archive/2026-09-08/codex/2.4.0-task4-scope-discovery` | merged |
| `snapshot/20260707-current-state` | `8f5409bbd07559004f91773e397f8be4ec56044c` | `archive/2026-09-08/snapshot/20260707-current-state` | archive-only |

The origin fix branch was still at 365b7ab before consolidation; it is an ancestor of the archived local tip 7def513 and both values are recorded in the annotated tag. All original refs also have a verified local Git bundle at .blend-analysis/2026-09-08-branch-consolidation/refs-before.bundle. The existing detached budget-baseline worktree remains intact as acceptance evidence.

Earlier lifecycle records above describe historical branch names. After successful synchronization, these names resolve through the archive tags listed here, and origin has only main. Version tags and published Releases are unchanged. Consolidation does not qualify a new release.
