# ChemBlender Agent Knowledge Base

This tracked directory provides task recovery and project-specific rules without injecting full development history into every conversation.

## Recovery Order

1. Read root `AGENTS.md`.
2. Read this index.
3. Read the relevant `active/` or `queued/` document.
4. Read only the referenced `reference/`, `decisions/`, or `completed/` document.
5. Verify dynamic Git, Blender, dependency, test, and CI state live.

Historical documents provide provenance, not current status.

## Index

| State | Document | Responsibility |
| --- | --- | --- |
| active | [quantum-visualization-foundation.md](active/quantum-visualization-foundation.md) | Phase 0 semantic model and data-boundary decisions |
| reference | [branch-architecture.md](reference/branch-architecture.md) | Maintained/upstream branch roles and lifecycle |
| reference | [dependencies-and-release.md](reference/dependencies-and-release.md) | Blender, RDKit, package, CI, and release gates |
| decision | [0001-version-and-extension-roadmap.md](decisions/0001-version-and-extension-roadmap.md) | 2.1.1 and 2.2.0 boundary rationale |
| decision | [0002-release-testing-and-pillow-scope.md](decisions/0002-release-testing-and-pillow-scope.md) | Release test runner, Pillow scope, and clean-profile rationale |
| decision | [0003-quantum-chemistry-semantic-model.md](decisions/0003-quantum-chemistry-semantic-model.md) | Phase 0 project registry, semantic objects, arrays, states, and provenance boundary |
| decision | [0004-grid3d-and-units.md](decisions/0004-grid3d-and-units.md) | Phase 0 affine grid, dataset axes, unit tokens, and conversion provenance |
| completed | [2.1.0-import-and-2.1.1-slimming.md](completed/2.1.0-import-and-2.1.1-slimming.md) | Legacy release history and evidence |
| completed | [2.2.0-extension-migration.md](completed/2.2.0-extension-migration.md) | Initial extension migration and local validation evidence |
| completed | [2.2.0-release-readiness.md](completed/2.2.0-release-readiness.md) | Published 2.2.0 package, install, merge, and CI evidence |
| documentation | [quantum visualization roadmap](../docs/quantum-visualization/roadmap.md) | Durable Phase 0–4 themes, gates, and priorities |

Repository-local extension workflow guidance remains under `skills/blender-mcp-skills/` and is locked by root `skills-lock.json`.

## Update Ownership

- Material current progress and the next action go to `active/`.
- Approved work not started goes to `queued/` when such a document is first needed.
- Stable reusable rules go to `reference/`.
- Architectural choices and consequences append under `decisions/`.
- Finished phases move to `completed/` with concise evidence.
- Regenerable runtime facts and caches go to ignored `.agents/cache/`.
- Polling with no state change produces no edit.
