# ChemBlender 2.3.0 Wave 4 Legacy Path and Scene Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route legacy UI through the unified import/project/view pipeline and provide a transactional, explicit migration wizard for 2.1/2.2 `.blend` scenes while preserving old objects as backups.

**Architecture:** Legacy code becomes a bridge, not a second parser. Scene migration performs detection, pure extraction, preview, staged project creation, new view creation and user confirmation. It never modifies old scenes automatically on load.

**Tech Stack:** Blender 5.1 API, existing legacy scaffold/CIF properties, new QCProject/import/view services, `unittest`, fixed `.blend` fixtures and Blender smoke.

## Global Constraints

- Opening an old `.blend` only detects and reports.
- Migration is explicit, undoable at the transaction level and leaves old objects intact by default.
- No source file or provenance is fabricated when absent.
- Legacy display properties become ViewSettings, not scientific properties.
- Old parser code is removed only after caller inventory and migration fixtures prove replacement.
- RC phase adds no new format scope.

---

### Task 1: Create and document legacy `.blend` fixtures

**Files:**
- Create: `tests/fixtures/legacy-blend/README.md`
- Add: `chemblender-2.1-molecule.blend`
- Add: `chemblender-2.2-crystal.blend`
- Add: `chemblender-2.2-edited-scaffold.blend`
- Create: `tests/test_legacy_fixture_inventory.py`

**Interfaces:**
- Produces: fixed old-scene evidence with hashes and expected recoverable fields.

- [ ] **Step 1: Build fixtures using the actual released versions**

Create one molecule with explicit bonds/orders and display settings, one CIF-derived crystal with cell/space group/occupancy/Uij, and one edited scaffold. Do not resave them with 2.3.0.

- [ ] **Step 2: Record provenance**

README records ChemBlender version, Blender version, generation steps, SHA-256, object/collection names and expected fields. Binary fixtures are reviewed for redistributable content.

- [ ] **Step 3: Add inventory tests**

Assert files/hashes and expected companion metadata. Commit fixtures separately before migration code.

### Task 2: Implement non-mutating legacy detection and extraction

**Files:**
- Create: `ChemBlender/legacy/detection.py`
- Create: `ChemBlender/legacy/extraction.py`
- Create: `ChemBlender/legacy/__init__.py`
- Create: `tests/test_legacy_detection_contract.py`
- Create: `tests/blender_legacy_extract.py`

**Interfaces:**
- Produces: `detect_legacy_scene()`, `extract_legacy_objects()` and `LegacyExtractionReport`.

- [ ] **Step 1: Write detection tests**

Open each fixture in background Blender and assert detection identifies legacy object types without creating/deleting/renaming any datablock. A new 2.3 project scene reports no legacy objects.

- [ ] **Step 2: Implement extraction to neutral snapshots**

Extract atom numbers/coordinates, edge topology/order, old radii/colors/scales, CIF original/current fields, cell, occupancy/Uij, object names and collections into immutable snapshots. Do not construct QCProject yet.

- [ ] **Step 3: Record ambiguity**

Unknown custom properties, missing source path, evaluated modifier geometry and nonuniform object transforms produce diagnostics. Apply object transform only according to a documented scientific-coordinate rule and show the effect in preview.

- [ ] **Step 4: Run and commit**

Run detection/extraction against fixtures and commit.

### Task 3: Build migration preview and project conversion

**Files:**
- Create: `ChemBlender/legacy/migration.py`
- Create: `tests/test_legacy_migration_core.py`
- Create: `docs/quantum-visualization/2.3.0/specs/legacy-migration-v1.md`

**Interfaces:**
- Produces: `plan_legacy_migration()`, `commit_legacy_migration()` and stable migration report.

- [ ] **Step 1: Write conversion tests**

Molecule snapshot maps to Structure, explicit TopologyRecord and ViewSettings. Crystal snapshot maps to periodic Structure/site data and declared symmetry. No source file creates provenance operation `legacy_blend_migration` with empty source hash and legacy object parents encoded as parameters.

- [ ] **Step 2: Separate scientific and view data**

Atomic number/coordinates/bonds/cell/occupancy/Uij are scientific. Colors/radii/material/node parameters are ViewSettings. Unverified fields receive Ambiguous/legacy_unverified diagnostics.

- [ ] **Step 3: Build a staged session**

Migration preview returns a staged QCProject and view plans. Commit uses ProjectTransaction/sidecar publication and does not touch old objects until new data and views verify.

- [ ] **Step 4: Run and commit**

Run pure conversion, sidecar and report tests; commit.

### Task 4: Implement Blender migration wizard and rollback

**Files:**
- Create: `ChemBlender/ui/migration.py`
- Modify: `ChemBlender/runtime/registration.py`
- Modify: `tests/blender_smoke.py`
- Create: `tests/blender_legacy_migrate.py`

**Interfaces:**
- Produces: legacy status panel, preview dialog, `Migrate to Project`, backup collection and rollback.

- [ ] **Step 1: Add load-time detection handler**

Handler stores a transient summary in session/UI state only. It does not write Scene project keys or alter legacy objects.

- [ ] **Step 2: Implement preview UI**

List objects, recoverable fields, diagnostics, proposed project entities, new view names and sidecar destination. Require explicit confirmation.

- [ ] **Step 3: Implement commit and backup**

Create/verify project and new views. Then link legacy objects into or move them to `ChemBlender Legacy Backup`, preserve original collection references in migration report, hide the backup by default and never delete it.

- [ ] **Step 4: Implement rollback**

On any failure, remove new views/project link/staged sidecar, restore any collection moves/hide state and leave original file dirty state unchanged except for user-visible error log.

- [ ] **Step 5: Run fixture smoke and commit**

Migrate all fixtures, save/reopen, verify new entities and backup objects. Commit.

### Task 5: Route all migrated legacy UI actions to the unified backend

**Files:**
- Modify: `ChemBlender/panel.py`
- Modify: `ChemBlender/scaffold.py`
- Modify: `ChemBlender/read.py`
- Modify: `ChemBlender/output.py`
- Create: `ChemBlender/legacy/reader_bridge.py`
- Create: `ChemBlender/legacy/scaffold_bridge.py`
- Create: `tests/test_legacy_operator_routing.py`

**Interfaces:**
- Produces: familiar old controls backed by ImportRequest, ProjectSession, StructureViewBuilder and core exporters.

- [ ] **Step 1: Inventory old callers**

Use static search and tests to list every call to `read_MOL`, `read_Cryst`, `read_cif`, `read_poscar`, old export block helpers and direct scaffold construction. Store the inventory in the active task and tests for migrated operator IDs.

- [ ] **Step 2: Route File/SMILES/PubChem**

File and SMILES create ImportRequest. PubChem network action downloads to an owned staging source with source URL/hash and then uses SDF reader. Network failures become diagnostics.

- [ ] **Step 3: Route CIF/POSCAR and exporters**

Use the built-in readers and core export plans. Existing labels and common operator IDs can remain for user continuity.

- [ ] **Step 4: Bridge editing tools**

Tools that expect scaffold attributes operate on the unified StructureView contract. Scientific modifications require Apply Scientific Edits; purely visual tools remain direct view operations.

- [ ] **Step 5: Run and commit**

Run old operator regression, new product flows and Blender smoke. Commit routing before deleting code.

### Task 6: Remove proven dead duplicate parser/export code

**Files:**
- Modify or delete: dead portions of `ChemBlender/read.py`, `ChemBlender/output.py`, `_math.py` and compatibility modules
- Modify: `.agents/reference/code-architecture-guide.md`
- Modify: tests.

**Interfaces:**
- Produces: one active parser/exporter per base format and a documented compatibility boundary.

- [ ] **Step 1: Prove zero callers**

AST/static test and `git grep` show no runtime caller for each candidate. Migration fixture code may retain isolated helpers until replaced.

- [ ] **Step 2: Delete in small commits by format family**

Remove old molecular paths, run tests/Blender smoke; commit. Remove old crystal paths, run tests/smoke; commit. Remove dead export blocks only after core exporter bridge passes.

- [ ] **Step 3: Update architecture and deprecation docs**

Document remaining legacy modules and planned 2.4 cleanup. No stale path remains in guide.

- [ ] **Step 4: Run full migration gate**

All old fixtures and current product flows pass. Record code reduction and known limits.
