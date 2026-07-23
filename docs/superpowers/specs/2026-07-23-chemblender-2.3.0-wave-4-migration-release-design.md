# ChemBlender 2.3.0 Wave 4 Migration and Release Qualification Design

## Status

Approved direction for `2.3.0-rc.1` and final, dependent on Wave 3.

## 1. Goal

Unify legacy entry points, migrate old scenes safely, harden performance and CI, complete documentation and release the exact verified artifact. No new format or dependency scope enters after RC.

## 2. Legacy UI bridge

Existing Build Molecules, File, SMILES, PubChem, CIF and POSCAR actions preserve familiar labels where useful but call the unified ImportRequest pipeline. `read.py` becomes a compatibility bridge or is reduced to functions still needed by migration. No format is parsed independently in both old and new paths.

A deprecation inventory proves callers before removal. Dead legacy code is removed only after fixed old-scene and operator tests pass.

## 3. Migration wizard

### Detection

On file load, scan for legacy object properties and collections without modifying them. Display a non-blocking status.

### Preview

List each old object, recoverable fields, ambiguous fields, unsupported fields, proposed Structure/Topology/View and sidecar destination.

### Commit

- build a temporary project;
- convert atom/bond/cell/occupancy/Uij data;
- create new views;
- verify project and views;
- move legacy objects into hidden backup collection;
- save only after user confirmation.

Failure removes temporary data and preserves old objects exactly. Migration provenance is `legacy_blend_migration`; missing source files are not fabricated.

## 4. CI architecture

### Native core job

Runs all base models/readers/exporters/import pipeline and document tests on Windows Python compatible with Blender.

### Optional core job

Uses pinned environments and submodule/fixture inputs for cclib, IOData, GBasis and other changed optional adapters. Target tests must report zero skips.

### Blender package job

Builds official ZIP, isolated install, Quick Import/UI/view/session smoke, real user-default cold-process test, lifecycle and assets.

### Release contract job

Validates tag/version, downloads exact artifact, verifies hashes, size, wheel inventory, licenses and release notes. Prerelease and final flags differ.

## 5. Versioning

Wave 0 recorded the Blender manifest prerelease probe. Wave 4 uses the verified scheme. All filenames derive from manifest/release metadata; no literal `2.2.0` remains in generic workflow logic.

Pre-releases are GitHub pre-releases and never latest. Final is latest only after all gates pass. Release workflow does not rebuild.

## 6. Performance qualification

- publish reference hardware and dataset hashes;
- run enable/import/view/save/reopen/filter/frame benchmarks;
- compare to prior prerelease and budget;
- investigate regressions before RC;
- verify cancel and temporary cleanup.

## 7. Documentation

Required:

- installation and upgrade;
- Quick Import and Project Browser;
- format maturity and loss policy;
- quality statuses and diagnostics;
- session/sidecar recovery;
- scientific editing and topology;
- Reader API v1 and example plugin;
- optional worker configuration;
- legacy migration;
- troubleshooting;
- changelog and release notes.

The root README and manifest tagline describe the actual product. Existing architecture guide and `.agents` indexes are updated in the same commits as responsibility changes.

## 8. Final release criteria

- All Wave scopes complete.
- No unresolved release-blocking diagnostics or data-corruption bugs.
- No targeted integration test skips.
- No unreviewed dependency or artifact growth.
- 2.2.x upgrade and legacy migration verified.
- RC received user testing; only fixes landed afterward.
- Exact annotated final tag artifact passes read-only release dry-run and publish authorization.
