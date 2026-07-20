# ChemBlender 2.2.0 Repository Governance Design

## Goal

Starting with 2.2.0, turn the repository into a maintainable development workspace while keeping every new Agent session consistent, auditable, and independent of chat history.

## Confirmed Release Boundaries

- `78c2d8d` remains the imported 2.1.0 baseline.
- 2.1.1 remains a legacy add-on and contains only the compressed `.blend` assets plus the version change to 2.1.1.
- 2.2.0 is the first Blender extension release.
- The extension source moves into root-level `ChemBlender/`; the repository root becomes the development workspace.
- RDKit wheel localization belongs to the 2.2.0 extension migration.
- `ChemBlender/wheels/*.whl` remains local and ignored. CI later downloads a pinned wheel into the release package.
- NumPy uses Blender's bundled installation.

## Design Choice

Use a tracked, layered knowledge base.

The root `AGENTS.md` is injected into new sessions, but it contains only stable rules and navigation. It must not accumulate chat transcripts, current commit IDs, CI run IDs, or command-by-command progress. Traceability comes from linked files under `.agents/`, Git history, and durable documentation under `docs/`.

This adapts the useful parts of the PySCF layout while changing one important policy: PySCF keeps its Agent knowledge local to avoid polluting upstream contributions; ChemBlender's maintained downstream branch tracks its stable Agent knowledge because it is part of the long-term development environment.

## Repository Layout

```text
AGENTS.md
docs/
├── README.md
├── development/
├── migration/
└── release/
.agents/
├── README.md
├── skills/
├── active/
├── queued/
├── reference/
├── decisions/
├── completed/
├── archive/
└── cache/
ChemBlender/
├── blender_manifest.toml
├── wheels/
└── ... extension source
skills-lock.json
```

Only create a directory when its first real document is added. Empty future scaffolding is not required.

## Content Responsibilities

### `AGENTS.md`

Keep it near 100–150 lines and limit it to:

- project identity and release boundaries;
- recovery and required-reading order;
- repository layout and file ownership;
- branch, upstream PR, dependency, wheel, and release rules;
- coding and verification requirements;
- links to current Agent knowledge.

Dynamic state must live elsewhere and must be verified before use.

### `.agents/`

- `README.md`: index, recovery order, and update ownership.
- `skills/`: repository-local skills and extension templates.
- `active/`: the only authoritative current task state, including goal, confirmed facts, next action, and verification.
- `queued/`: approved work that has not started.
- `reference/`: stable operational rules such as branch architecture, Blender runtime, dependencies, wheel packaging, and release verification.
- `decisions/`: numbered decision records explaining choices and consequences.
- `completed/`: concise summaries and evidence links for finished phases; never used as current status.
- `archive/`: lightweight indexes for retained historical evidence.
- `cache/`: regenerable local data only.

The existing `blender-mcp-skills` directory and `skills-lock.json` are tracked so the extension template and its provenance are reproducible.

### `docs/`

`docs/` is human-facing and contains durable development, migration, and release documentation. It must not duplicate live task status from `.agents/active/`.

## Session Recovery Flow

After a new conversation or context compaction:

1. Read root `AGENTS.md`.
2. Read `.agents/README.md`.
3. Read the relevant `.agents/active/` or `.agents/queued/` document.
4. Read only the referenced decision or reference documents needed for the task.
5. Re-check Git state, remotes, Blender runtime, dependency versions, tests, and CI before treating dynamic information as current.

Historical documents provide provenance, not live status.

## Initial Knowledge Directions

The first 2.2.0 governance commit creates only these documents:

- `.agents/README.md`
- `.agents/active/2.2.0-extension.md`
- `.agents/reference/branch-architecture.md`
- `.agents/reference/dependencies-and-release.md`
- `.agents/decisions/0001-version-and-extension-roadmap.md`
- `.agents/completed/2.1.0-import-and-2.1.1-slimming.md`
- `docs/README.md`
- `docs/development/branch-and-release.md`
- `docs/migration/2.2.0-extension.md`

Additional files are split out only when one of these documents becomes difficult to navigate.

## Branch and Release Model

1. Preserve the current extension experiment as `archive/extension-spike-20260707`.
2. Create `release/2.1.1` from `78c2d8d`.
3. Apply only `.blend` compression and the 2.1.1 legacy add-on version change.
4. Merge the result into the maintained `main` and tag `v2.1.1`.
5. Create `feat/2.2.0-extension` from that maintained `main`.
6. Establish repository governance before moving the add-on into `ChemBlender/` and completing the extension migration.

The fork retains two baselines:

- `origin/main`: maintained ChemBlender release line;
- `upstream/main`: upstream reference line.

Any future upstream contribution starts from the then-current `upstream/main` on an `upstream-pr/*` branch and contains only the necessary code and tests. Downstream governance, packaging, and extension history are not included.

## Ignore and Evidence Policy

Track stable instructions, decision records, summaries, skills, and indexes. Ignore:

- `ChemBlender/wheels/*.whl`;
- `.agents/cache/`;
- large files below `.agents/archive/` while retaining its index;
- `.blend-analysis/`;
- extension build ZIPs and other regenerable build output;
- linked worktrees under `.worktrees/`.

CI release jobs must download a pinned RDKit wheel, verify its checksum, place it under `ChemBlender/wheels/`, validate the extension, build the ZIP, and retain the resulting package as an artifact.

## Update Rules

- Update `active/` only after a material state change; polling without change produces no document edit.
- Record branch-role, release-boundary, dependency-source, or packaging-policy changes in the same commit as the change.
- Append a new decision record instead of rewriting the rationale for an old decision.
- Move a finished task from `active/` to `completed/` with a concise result and evidence entry.
- Never infer current state from `completed/`, archived evidence, or root `AGENTS.md`.

## Verification

Repository governance is accepted when:

- `AGENTS.md` and every indexed knowledge document are tracked and readable as UTF-8 without BOM;
- all links in `AGENTS.md`, `.agents/README.md`, and `docs/README.md` resolve;
- `git check-ignore` confirms wheel, cache, build, and large evidence files are ignored;
- `git diff --check` passes;
- the 2.1.1 release contains no manifest, extension namespace fixes, or tracked wheel;
- the 2.2.0 extension validates and builds with Blender's extension tooling;
- the built package contains the pinned RDKit wheel while the repository does not track it;
- a clean extension installation can register, unregister, and reload in the target Blender runtime.

## Non-goals

- Do not preserve full chat transcripts in the repository.
- Do not build a custom memory database or synchronization tool.
- Do not add speculative documentation categories or empty directories.
- Do not mix 2.2.0 extension work into the 2.1.1 legacy add-on release.
- Do not change Git remotes or push branches as part of repository setup without explicit approval.
