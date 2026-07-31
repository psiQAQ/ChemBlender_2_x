# Changelog

All notable changes to the maintained ChemBlender release line are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow semantic versioning.

## [Unreleased]

## [2.3.0-rc.1] - 2026-07-31

### Added

- Added native XYZ/extXYZ, Cube, MOL2, PDB/PQR and POSCAR/CONTCAR readers, plus RDKit-backed MOL/SDF/SMILES and Gemmi-backed CIF readers, mapped into one vendor-neutral Project model.
- Added first-class Structure, topology, trajectory/property, crystal/symmetry, Grid3D/Surface and biological/exchange records with immutable source revisions and provenance.
- Added Project Browser export workflows for extXYZ, MOL, SDF, SMILES, CIF and POSCAR at F5 maturity with explicit loss preview; XYZ export is F4 and intentionally writes one structure's coordinates only. CJSON and QCSchema provide controlled core-envelope export paths.
- Added scientific editing, explicit/inferred topology selection, unified molecular/crystal Structure views, periodic views, Grid3D Volume/Surface workflows, background task cancellation and paged Project Browser projections.
- Added Reader API `1.0-rc1`, explicit Extension reader discovery/conformance, generated format/dependency capability documents and deterministic diagnostic export.
- Added explicit legacy 2.1/2.2 scene preview and migration with hash-locked fixture evidence, original-object backup ownership and save/reopen verification.

### Changed

- Froze the sidecar/project schema at `1.0` and Reader API at `1.0-rc1` for the RC scope; post-RC work is limited to release-blocking fixes and documentation clarity.
- Made the `.blend` plus same-basename `.cbq/` pair the durable project boundary; scientific arrays and provenance remain authoritative while VDB and mesh products remain rebuildable derived caches.
- Bundled exact Windows CPython 3.13 wheels for RDKit `2026.3.3` and Gemmi `0.7.5`; external scientific stacks remain optional worker/runtime backends.
- Added bounded benchmark, cancellation, diagnostics, revision-selection and recovery workflows without placing large scientific arrays in Blender RNA.

### Fixed

- Canonicalized explicit and inferred topology records, including periodic image shifts and unwrapped-coordinate invariance, and made new CJSON topology immediately available without save/reopen migration.
- Hardened project adoption, multi-Scene links, sidecar publication, cache repair and import/relink rollback so failures retain the previous verified project or report recoverable residuals.
- Preserved Grid3D native coordinates, units, Cube nuclear charges/dataset metadata, crystal fractional coordinates, occupancy, symmetry and supported biological/exchange annotations through project and sidecar round trips.
- Made cancellable import/export/worker jobs clean their owned staging state and prevented stale browser/revision/cache state from being presented as current data.

### Compatibility

- Supports Blender 5.1.0 or later on Windows x64; release qualification uses Blender 5.1.2 and its bundled Python 3.13.
- The base ZIP includes RDKit and Gemmi. cclib, IOData, GBasis, ASE, pymatgen, phonopy, spglib and large external programs are not bundled base requirements and remain explicitly availability-gated.
- Sidecar v0.1/v0.2 projects are integrity-checked and migrated in memory; a successful 2.3 save publishes schema v1 rather than rewriting the old source in place.
- Reader and export maturity is format-specific. MOL2, PDB/PQR and Cube have no general Project Browser writer in this RC; import support must not be interpreted as lossless round-trip support.

### Migration

- Back up the complete `.blend`/`.cbq` pair, close all Blender processes, verify the official ZIP checksum and install the Extension from a cold process before opening the working copy.
- Prefer **Save As** for the first schema-v1 publication. A v1 sidecar cannot be downgraded for ChemBlender 2.2; rollback requires restoring the paired pre-upgrade backup.
- Legacy direct-object scenes require the explicit preview/confirm wizard. Original objects move to `ChemBlender Legacy Backup`; the migration is not claimed to be lossless and has no automatic post-success undo.

### Known Limitations

- This RC is Windows x64 only. Loaded RDKit or Gemmi DLLs can keep isolated-profile files locked until Blender exits; a successful process exit and fresh-profile reinstall remain the functional checks.
- Optional readers/workers are unavailable unless their separately managed runtime passes the exact availability check; the base package does not install or download them.
- MOL2 and PDB/PQR export remain readiness-only, Cube has no lossless re-export, and XYZ export intentionally omits trajectory/property semantics. Lossy Project Browser exports require preview and confirmation.
- Scripted usability acceptance covers the packaged workflows and hash-locked fixtures but is not an independent human-participant study.
- Remote CI has not run for this exact RC commit. Local qualification evidence must not be described as exact-HEAD CI evidence.

### Verification

- The local RC gate covers the full standard-library suite, generated-document freshness, dependency hashes/licenses, native Extension validation/build, ZIP path/type/CRC/member audits, isolated installation, two lifecycle reloads, product smoke and three legacy save/reopen fixtures.
- Performance and usability evidence is recorded under `docs/quantum-visualization/2.3.0/`; package size and section baselines retain zero unexplained-growth allowances.
- `Remote CI: Not Run`. Tagging, package CI and prerelease publication require separate authorization and exact-tag evidence.

## [2.3.0-alpha.1] - 2026-07-26

### Added

- Added one authoritative project session per `.blend`, with atomic multi-Scene `.cbq` links and durable save/reopen persistence.
- Added transactional import and relink recovery that restores all affected Scene links after a failed commit.
- Added explicit extension registration, drag-and-drop and Quick Import flows, a Project Browser, and import conflict/grouping decisions.
- Added format-aware default Structure, Grid3D volume, and signed-isosurface views for XYZ and Cube data.
- Added durable derived Volume and Surface caches under the project sidecar, including missing-cache reconstruction.
- Added a manually dispatched Release workflow that publishes only the exact successful tag CI artifact.
- Added deterministic ZIP, checksum, manifest, wheel, and Release asset digest verification.
- Added versioned changelog extraction so GitHub Release notes come from this file.

### Fixed

- Release verification can inspect artifacts from tags created before the Release workflow existed.
- Manifest comparison now ignores platform line-ending differences while preserving TOML field validation.
- Shortened same-directory atomic temporary paths so complete product flows work with default Windows temporary and user paths.

## [2.2.0] - 2026-07-21

### Added

- Added the `ChemBlender/` Blender Extension layout and `blender_manifest.toml`.
- Bundled the pinned RDKit 2026.3.3 CPython 3.13 Windows x64 wheel for offline installation.
- Added repository contracts, isolated Blender installation tests, package auditing, and Windows package CI.

### Changed

- Migrated the maintained legacy add-on to Blender's extension-native installation and module namespace.
- Reused Blender-provided NumPy and Requests; Pillow remains unbundled because ChemBlender does not use it.
- Hardened register, unregister, repeated reload, and packaged `.blend` library handling.

### Compatibility

- Blender 5.1.0 or later.
- Windows x64.

### Installation

- Download `chemblender-2.2.0.zip` and `chemblender-2.2.0.sha256` from the GitHub Release.
- Verify the checksum, then install the ZIP directly through Blender's **Install from Disk** extension action without extracting it.

### Verification

- The published ZIP is the exact artifact from the successful [`v2.2.0` package workflow](https://github.com/psiQAQ/ChemBlender_2_x/actions/runs/29789621435).
- ZIP SHA-256: `65f157c9d6af89ecc81e426ff866f4c9be5e99c713abe51e9e5d5b67bd5005a5`.
- The package passed manifest validation, clean-profile installation, RDKit 3D embedding, two extension lifecycle cycles, and both `.blend` library checks.

### Known Limitations

- Disabling the extension after RDKit has loaded may report file-removal warnings on Windows because native DLLs remain locked until Blender exits.

## [2.1.1] - 2026-07-21

### Changed

- Published the final legacy add-on release.
- Compressed `Chem_Nodes.blend` from 17,887,213 to 1,189,463 bytes.
- Compressed `Chem_Nodes_En.blend` from 17,764,762 to 1,209,480 bytes.
- Updated the legacy add-on version to 2.1.1 without adding extension packaging or runtime dependency changes.

### Verification

- Both optimized `.blend` libraries opened successfully in Blender 5.1.2 and preserved their expected objects and node groups.

## [2.1.0] - 2026-07-07

### Changed

- Imported the latest ChemBlender 2.1.0 source as commit `78c2d8d8d6361302bf8f19a568c3d7cfccde4c19`, based on upstream commit `9077096b776cd18ca85adb4b50253a0d3c18fd76`.

[Unreleased]: https://github.com/psiQAQ/ChemBlender_2_x/compare/v2.3.0-rc.1...HEAD
[2.3.0-rc.1]: https://github.com/psiQAQ/ChemBlender_2_x/releases/tag/v2.3.0-rc.1
[2.3.0-alpha.1]: https://github.com/psiQAQ/ChemBlender_2_x/releases/tag/v2.3.0-alpha.1
[2.2.0]: https://github.com/psiQAQ/ChemBlender_2_x/releases/tag/v2.2.0
[2.1.1]: https://github.com/psiQAQ/ChemBlender_2_x/releases/tag/v2.1.1
[2.1.0]: https://github.com/psiQAQ/ChemBlender_2_x/commit/78c2d8d8d6361302bf8f19a568c3d7cfccde4c19
