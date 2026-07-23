# ChemBlender 2.3.0 Wave 2 Crystal View, Export and Optional Symmetry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify crystal visualization for CIF and POSCAR, expose occupancy/ADP/constraints, keep spglib optional, and freeze the 2.3.0 sidecar schema and Reader API v1 RC.

**Architecture:** The unified StructureViewBuilder receives periodic structures and optional site datasets. Crystal display operations create derived view geometry, not scientific atom duplication. Symmetry derivation runs through an optional service and returns new project entities.

**Tech Stack:** Blender Geometry Nodes, NumPy, bundled Gemmi, optional spglib worker/core environment, existing crystal node assets, `unittest` and Blender smoke.

## Global Constraints

- CIF/POSCAR views share one periodic structure contract.
- Asymmetric unit, expanded cell and supercell are view choices.
- Occupancy and ADP data are source datasets.
- spglib absence is non-blocking.
- Beta.1 freezes sidecar schema and Reader API v1 RC after this plan.

---

### Task 1: Define periodic ViewSettings and site attributes

**Files:**
- Create: `ChemBlender/views/periodic.py`
- Modify: `ChemBlender/views/structure.py`
- Create: `tests/test_periodic_view_settings.py`
- Modify: `tests/blender_smoke.py`

**Interfaces:**
- Produces: `PeriodicViewSettings`, `create_periodic_structure_view()` and named attribute contract.

- [ ] **Step 1: Define settings**

```python
@dataclass(frozen=True, slots=True)
class PeriodicViewSettings:
    representation: str = "source_sites"
    supercell: tuple[int, int, int] = (1, 1, 1)
    boundary_tolerance: float = 1e-5
    show_cell: bool = True
    show_axes: bool = False
    occupancy_mode: str = "opacity"
    adp_probability: float = 0.50
    show_constraints: bool = True
```

Validate representation values and positive supercell.

- [ ] **Step 2: Add site attributes**

Write occupancy, site ID, disorder group, ADP type/covariance components and Selective Dynamics to point attributes. String labels use categorical codes and mapping metadata.

- [ ] **Step 3: Test no scientific duplication**

Source-sites view has exactly source atom count. Expanded/supercell display uses instances/derived geometry and ViewRecord settings; QCProject structure remains unchanged.

- [ ] **Step 4: Run and commit**

Run periodic view and Blender smoke; commit.

### Task 2: Integrate existing cell, supercell, polyhedra and ADP nodes

**Files:**
- Modify: `ChemBlender/node.py`
- Modify: `ChemBlender/crys_utils.py`
- Modify: `ChemBlender/views/periodic.py`
- Create: `tests/test_crystal_node_contract.py`
- Modify: `tests/blender_smoke.py`

**Interfaces:**
- Produces: versioned Geometry Node contracts for cell, supercell, occupancy and ellipsoid display.

- [ ] **Step 1: Add node contract metadata tests**

Each loaded/generated node group has `cbq_contract` and version. Incompatible existing groups with the same name are rejected or namespaced, not silently reused.

- [ ] **Step 2: Adapt inputs to full cell matrix**

Do not reduce all periodic calculations to lengths/angles when a full matrix is available. Pass vectors or transform matrices to new node wrappers; preserve old nodes for legacy bridge.

- [ ] **Step 3: Occupancy and ADP**

Occupancy can control opacity/radius/pie or split-site modes defined by settings. Ellipsoids use stored U tensor and probability parameter; missing/partial rows fall back visibly and carry quality badge.

- [ ] **Step 4: Verify and commit**

Blender smoke covers oblique cell, partial occupancy and Uij. Commit.

### Task 3: Add optional spglib service and discrepancy UI

**Files:**
- Create: `ChemBlender/core/symmetry_service.py`
- Modify: `ChemBlender/core/spglib_adapter.py`
- Create: `tests/test_symmetry_service.py`
- Modify: `ChemBlender/ui/properties.py`
- Modify: `ChemBlender/ui/project_browser/panel.py`

**Interfaces:**
- Produces: `symmetry_availability()`, `derive_structure_symmetry()` and comparison rows.

- [ ] **Step 1: Test missing dependency**

When spglib is absent, availability returns false/reason, derive action is disabled, CIF/POSCAR project remains Complete if its source data is complete.

- [ ] **Step 2: Test derived result**

With a fake/integration adapter, record symprec, angle tolerance, program version and transformations. Result and standardized structure are separate entities.

- [ ] **Step 3: Implement comparison UI**

Show declared vs derived numbers/symbols, match status, tolerance and links to standardized structure. User may create a view of standardized structure; source view remains.

- [ ] **Step 4: Run and commit**

Run no-dependency unit path always; integration path in optional CI. Commit.

### Task 4: Complete crystal export UX

**Files:**
- Modify: `ChemBlender/ui/export.py`
- Modify: `ChemBlender/ui/project_browser/panel.py`
- Create: `tests/test_crystal_export_ui_contract.py`
- Modify: `tests/blender_smoke.py`

**Interfaces:**
- Produces: CIF Preserve/Normalized choices and POSCAR settings with loss preview.

- [ ] **Step 1: Implement export plan preview**

List target format, source/derived structure, fields preserved/changed/omitted, quality warnings and output path. Partial/Ambiguous requires a confirmation checkbox.

- [ ] **Step 2: Prevent view geometry export as science**

Supercell/expanded display is not exported unless the user explicitly derives a new periodic structure. Export uses selected project Structure, not evaluated Blender mesh.

- [ ] **Step 3: Blender smoke**

Export source CIF Preserve, derived normalized CIF and POSCAR with Selective Dynamics; parse outputs and compare semantics.

- [ ] **Step 4: Commit**

Commit UI and smoke.

### Task 5: Freeze sidecar schema and Reader API v1 RC

**Files:**
- Modify: `ChemBlender/reader_api/version.py`
- Modify: `ChemBlender/reader_api/manifest.py`
- Modify: `ChemBlender/core/sidecar.py`
- Create: `docs/quantum-visualization/2.3.0/reader-api-v1-rc.md`
- Create: `docs/quantum-visualization/2.3.0/specs/cbq-sidecar-v1.md`
- Modify: compatibility tests.

**Interfaces:**
- Produces: Reader API `1.0-rc1` or the repository-approved comparable version token, sidecar schema `1.0`, and migration from 0.1/0.2.

- [ ] **Step 1: Create exhaustive public schema snapshots**

Canonical documents for every public entity type and reader manifest are committed as fixtures with hashes. Tests reject field removal/rename and allow documented optional additions only.

- [ ] **Step 2: Update version and compatibility rules**

Plugin manifests declare compatible range. Old 0.x experiment plugins fail with a clear compatibility diagnostic, not extension registration failure.

- [ ] **Step 3: Sidecar migration tests**

Open v0.1, v0.2 and v1 fixtures. Saving writes v1 only. Migration preserves entities/arrays and creates defaults for absent new registries.

- [ ] **Step 4: Run full beta.1 gate**

Run pure, real native, optional symmetry, Blender package, Gemmi lifecycle, size and migration tests.

- [ ] **Step 5: Commit freeze**

Commit API/schema/specs/tests as one reviewed architecture milestone. After this commit, breaking changes require a release-blocking ADR.
