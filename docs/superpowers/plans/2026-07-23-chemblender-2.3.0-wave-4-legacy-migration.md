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

- [x] **Step 1: Build fixtures using the actual released versions**

Create one molecule with explicit bonds/orders and display settings, one CIF-derived crystal with cell/space group/occupancy/Uij, and one edited scaffold. Do not resave them with 2.3.0.

- [x] **Step 2: Record provenance**

README records ChemBlender version, Blender version, generation steps, SHA-256, object/collection names and expected fields. Binary fixtures are reviewed for redistributable content.

- [x] **Step 3: Add inventory tests**

Assert files/hashes and expected companion metadata. Commit fixtures separately before migration code.

**Task 1 checkpoint (2026-07-30):**

- Prepared commits `ab29560a54557ca4bb794e9e8043cd2110abc10b` and
  `e26319dd7697e49373840e00dbfbb13270b5cc42` were integrated in order as
  `63b298ad39f374d3e19777b62d01f3e96b8a0b13` and
  `69665c329395449e468f23fa7b954a9b58df4f08`.
- Inventory tests: 3 passed; complete suite: 1811 passed, 26 skipped,
  0 failed; documentation contracts: 16 passed.
- Blender 5.1.2 independently reopened all three fixtures without linked
  libraries or external file images. `compileall` and `git diff --check`
  passed.

### Task 2: Implement non-mutating legacy detection and extraction

**Files:**
- Create: `ChemBlender/legacy/detection.py`
- Create: `ChemBlender/legacy/extraction.py`
- Create: `ChemBlender/legacy/__init__.py`
- Create: `tests/test_legacy_detection_contract.py`
- Create: `tests/blender_legacy_extract.py`

**Interfaces:**
- Produces: `detect_legacy_scene()`, `extract_legacy_objects()` and `LegacyExtractionReport`.

- [x] **Step 1: Write detection tests**

Open each fixture in background Blender and assert detection identifies legacy object types without creating/deleting/renaming any datablock. A new 2.3 project scene reports no legacy objects.

- [x] **Step 2: Implement extraction to neutral snapshots**

Extract atom numbers/coordinates, edge topology/order, old radii/colors/scales, CIF original/current fields, cell, occupancy/Uij, object names and collections into immutable snapshots. Do not construct QCProject yet.

- [x] **Step 3: Record ambiguity**

Unknown custom properties, missing source path, evaluated modifier geometry and nonuniform object transforms produce diagnostics. Apply object transform only according to a documented scientific-coordinate rule and show the effect in preview.

- [x] **Step 4: Run and commit**

Run detection/extraction against fixtures and commit.

**Task 2 checkpoint (2026-07-30):**

- Implementation `85870573586f196f3860c2141b97a829721287f1`,
  review fix `9ed363c0ace00b089cc11af56f13a5c1565ac544`, and final-review
  fix `10c561df95be6171858e373063354dd460eebbe2`.
- Detection/extraction stays read-only, returns frozen Blender-neutral
  snapshots, uses base-mesh coordinates transformed by `matrix_world`, and
  records ambiguity without consuming evaluated geometry.
- Blender 5.1.2 contracts cover all three fixtures, factory/current
  StructureView scenes, mixed current/legacy scenes, parent-induced world
  transforms, and unchanged datablock inventories.
- Focused inventory/detection/documentation: 24 passed; complete suite:
  1816 passed, 26 skipped, 0 failed. Outside-Blender import, extension
  validate, `compileall`, and `git diff --check` passed.

### Task 3: Build migration preview and project conversion

**Files:**
- Create: `ChemBlender/legacy/migration.py`
- Create: `tests/test_legacy_migration_core.py`
- Create: `docs/quantum-visualization/2.3.0/specs/legacy-migration-v1.md`

**Interfaces:**
- Produces: `plan_legacy_migration()`, `commit_legacy_migration()` and stable migration report.

- [x] **Step 1: Write conversion tests**

Molecule snapshot maps to Structure, explicit TopologyRecord and ViewSettings. Crystal snapshot maps to periodic Structure/site data and declared symmetry. No source file creates provenance operation `legacy_blend_migration` with empty source hash and legacy object parents encoded as parameters.

- [x] **Step 2: Separate scientific and view data**

Atomic number/coordinates/bonds/cell/occupancy/Uij are scientific. Colors/radii/material/node parameters are ViewSettings. Unverified fields receive Ambiguous/legacy_unverified diagnostics.

- [x] **Step 3: Build a staged session**

Migration preview returns a staged QCProject and view plans. Commit uses ProjectTransaction/sidecar publication and does not touch old objects until new data and views verify.

- [x] **Step 4: Run and commit**

Run pure conversion, sidecar and report tests; commit.

**Task 3 checkpoint (2026-07-30):**

- Implementation `f848a8f9b820fe74e8c3c036700d31e3f1706408`;
  review fixes `d6e5283ec1b58c1ff9a17fe46899113cebbdae97`,
  `576f6e0f3acc85ee08f1d885b32276fd072f933d`, and
  `2837a03874181d867c2f24438625f7bd1a3b5ae7`.
- `LegacyMigrationPlan` owns the staged `QCProject`, view plans, report and
  content-bound base/candidate inventories. Commit rejects stale or modified
  plans before verified sidecar publication.
- Molecule and crystal conversion keeps scientific data in unified project
  entities, display data in frozen view settings, and only trusts a saved
  non-link `.blend` whose current SHA-256 still matches extraction-time proof.
- Focused migration/detection/inventory/publication/documentation verification:
  67 passed. Complete suite: 1842 passed, 26 skipped, 0 failed.
- Blender 5.1.2 fixture extraction, extension validate/build, ZIP CRC/path
  safety/inventory, outside-Blender import, `compileall`, and
  `git diff --check` passed. Independent closure review was clean.

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
