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
| active | [phase3-sidecar-cache.md](active/phase3-sidecar-cache.md) | `.cbq` sidecar manifest, lazy arrays and cache identity |
| reference | [branch-architecture.md](reference/branch-architecture.md) | Maintained/upstream branch roles and lifecycle |
| reference | [dependencies-and-release.md](reference/dependencies-and-release.md) | Blender, RDKit, package, CI, and release gates |
| decision | [0001-version-and-extension-roadmap.md](decisions/0001-version-and-extension-roadmap.md) | 2.1.1 and 2.2.0 boundary rationale |
| decision | [0002-release-testing-and-pillow-scope.md](decisions/0002-release-testing-and-pillow-scope.md) | Release test runner, Pillow scope, and clean-profile rationale |
| decision | [0003-quantum-chemistry-semantic-model.md](decisions/0003-quantum-chemistry-semantic-model.md) | Phase 0 project registry, semantic objects, arrays, states, and provenance boundary |
| decision | [0004-grid3d-and-units.md](decisions/0004-grid3d-and-units.md) | Phase 0 affine grid, dataset axes, unit tokens, and conversion provenance |
| decision | [0005-reader-capability-contract.md](decisions/0005-reader-capability-contract.md) | Phase 0 reader registry, sniffing, capability, import batch, and parser report contract |
| decision | [0006-blend-sidecar-boundary.md](decisions/0006-blend-sidecar-boundary.md) | Phase 0 authoritative sidecar, blend references, revisions, and cache invalidation boundary |
| decision | [0007-wavefunction-grid-backend.md](decisions/0007-wavefunction-grid-backend.md) | GBasis worker backend, uniform-grid scope, and Python compatibility boundary |
| decision | [0008-excited-state-and-spectrum-contract.md](decisions/0008-excited-state-and-spectrum-contract.md) | Excited-state identity, configuration, references and electronic-spectrum contract |
| decision | [0009-phase1-blender-dataset-contract.md](decisions/0009-phase1-blender-dataset-contract.md) | Structure, atom dataset, vector, trajectory and stick-selection Blender contract |
| decision | [0010-crystal-parsing-and-symmetry-boundary.md](decisions/0010-crystal-parsing-and-symmetry-boundary.md) | Gemmi CIF envelope, periodic sites and spglib standardization boundary |
| decision | [0011-periodic-structure-and-vasp-grid-boundary.md](decisions/0011-periodic-structure-and-vasp-grid-boundary.md) | ASE/pymatgen-core periodic structure, VASP scalar-field semantics and linked identity |
| decision | [0012-periodic-band-dos-boundary.md](decisions/0012-periodic-band-dos-boundary.md) | Band/DOS/projection axes, energy reference and Blender curve contract |
| decision | [0013-phonopy-complex-mode-boundary.md](decisions/0013-phonopy-complex-mode-boundary.md) | Phonopy complex q-point modes and periodic phase animation |
| decision | [0014-fermi-surface-worker-boundary.md](decisions/0014-fermi-surface-worker-boundary.md) | Neutral Fermi-surface mesh and optional PyProcar worker boundary |
| completed | [2.1.0-import-and-2.1.1-slimming.md](completed/2.1.0-import-and-2.1.1-slimming.md) | Legacy release history and evidence |
| completed | [2.2.0-extension-migration.md](completed/2.2.0-extension-migration.md) | Initial extension migration and local validation evidence |
| completed | [2.2.0-release-readiness.md](completed/2.2.0-release-readiness.md) | Published 2.2.0 package, install, merge, and CI evidence |
| completed | [quantum-visualization-foundation.md](completed/quantum-visualization-foundation.md) | Phase 0 semantic model, reader contract, and cross-format normalization evidence |
| completed | [molecular-quantum-chemistry-ingestion.md](completed/molecular-quantum-chemistry-ingestion.md) | Cube/OpenVDB, cclib, IOData, basis, and orbital ingestion evidence |
| completed | [wavefunction-derived-fields.md](completed/wavefunction-derived-fields.md) | GBasis MO/density grids, numerical baselines, and Blender Volume evidence |
| completed | [wavefunction-observables.md](completed/wavefunction-observables.md) | One-RDM, electron/spin density and ESP derived-field evidence |
| completed | [vibrations-and-spectra.md](completed/vibrations-and-spectra.md) | cclib vibrations, IR/Raman spectra and Blender mode-animation evidence |
| completed | [excited-states-and-spectra.md](completed/excited-states-and-spectra.md) | cclib excited states, UV-Vis/ECD spectra and transition-reference evidence |
| completed | [phase1-blender-adapters.md](completed/phase1-blender-adapters.md) | Phase 1 scalar/vector/trajectory/linked-selection Blender closure evidence |
| completed | [crystal-foundation.md](completed/crystal-foundation.md) | Gemmi/spglib periodic semantics, parsing and standardization evidence |
| completed | [periodic-structure-and-fields.md](completed/periodic-structure-and-fields.md) | ASE structures, VASP scalar fields, periodic Grid3D identity and Blender evidence |
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
