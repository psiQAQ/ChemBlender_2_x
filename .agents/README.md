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
| active | [phase4-external-analysis-adapters.md](active/phase4-external-analysis-adapters.md) | Safe external analysis adapter and failure-isolation contract |
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
| decision | [0015-cbq-npy-sidecar-and-cache-identity.md](decisions/0015-cbq-npy-sidecar-and-cache-identity.md) | `.cbq` v0.1 manifest, lazy arrays, atomic write and cache identity |
| decision | [0016-local-worker-v1-and-npy-retention.md](decisions/0016-local-worker-v1-and-npy-retention.md) | Strict local worker protocol, atomic output and `.npy` benchmark decision |
| decision | [0017-lazy-trajectory-frame-manager.md](decisions/0017-lazy-trajectory-frame-manager.md) | Per-frame lazy reads, bounded LRU and Blender trajectory lifecycle |
| decision | [0018-grid-lod-and-render-cache-identity.md](decisions/0018-grid-lod-and-render-cache-identity.md) | Reproducible Grid3D LOD and Blender render cache identity |
| decision | [0019-versioned-recipe-contract.md](decisions/0019-versioned-recipe-contract.md) | Versioned recipe definition, binding and validation contract |
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
| completed | [sidecar-and-cache-foundation.md](completed/sidecar-and-cache-foundation.md) | `.cbq` v0.1 sidecar, lazy arrays, cache keys and Blender scene link evidence |
| completed | [sidecar-benchmark-and-local-worker.md](completed/sidecar-benchmark-and-local-worker.md) | Representative `.npy` benchmark and local worker v1 evidence |
| completed | [lazy-trajectory-frame-manager.md](completed/lazy-trajectory-frame-manager.md) | Per-frame lazy trajectory access, LRU and Blender lifecycle evidence |
| completed | [grid-lod-and-volume-cache.md](completed/grid-lod-and-volume-cache.md) | Lazy Grid3D LOD derivation and reproducible Volume cache evidence |
| completed | [recipe-contract.md](completed/recipe-contract.md) | Strict recipe schema, binding and derivation identity evidence |
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
