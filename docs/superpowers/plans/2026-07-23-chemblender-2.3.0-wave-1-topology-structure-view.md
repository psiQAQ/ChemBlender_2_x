# ChemBlender 2.3.0 Wave 1 Topology and Unified Structure View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Version topology by source and quality, implement scalable distance/PBC inference, and replace point-only quantum structure views with a single topology-aware ball-and-stick contract compatible with legacy tools.

**Architecture:** `TopologyRecord` is a first-class project entity. `StructureViewBuilder` consumes a Structure and selected topology and emits one Mesh contract with vertices, edges, named attributes, Geometry Nodes and ViewRecord identity. Scientific edits create derived entities.

**Tech Stack:** NumPy, Blender Mesh/Geometry Nodes, RDKit for sanitized molecular topology, existing ChemBlender node libraries, `unittest` and Blender smoke.

## Global Constraints

- File topology is never overwritten by inference.
- Periodic/material connections do not default to chemical single bonds.
- No O(N²) full scan at target sizes.
- View changes do not mutate scientific data.
- Existing atom/bond editing operators remain usable through a documented bridge.

---

### Task 1: Introduce TopologyRecord and source/quality enums

**Files:**
- Modify: `ChemBlender/core/model/structure.py`
- Create: `ChemBlender/core/model/molecular_topology.py`
- Modify: `ChemBlender/core/model/project.py`
- Modify: `ChemBlender/core/model_registry.py`
- Create: `tests/test_topology_record.py`

**Interfaces:**
- Produces: `TopologySource`, `TopologyRecord`, project `topologies` registry and Structure topology references.

- [ ] **Step 1: Write validation tests**

Test bond index/order shapes, aromatic flags, stereo labels, source enum, quality, canonical inference parameters and structure reference. `distance_inferred` requires non-empty inference parameters; `explicit_file` permits none.

- [ ] **Step 2: Preserve MolecularTopology compatibility**

Keep the old type readable for v0.1 sidecars. Migration converts embedded Structure topology into a TopologyRecord with `explicit_file` when source came from an explicit format, otherwise `distance_inferred` plus legacy parameters if known. Ambiguous origin becomes `legacy_unverified` quality.

- [ ] **Step 3: Update project validation and sidecar migration**

A Structure can reference zero or more topology IDs; selected topology is view state, not structure state.

- [ ] **Step 4: Run and commit**

Run model, migration, existing readers and sidecar tests; commit.

### Task 2: Implement scalable nonperiodic topology inference

**Files:**
- Create: `ChemBlender/core/topology/infer.py`
- Create: `ChemBlender/core/topology/radii.py`
- Create: `tests/test_topology_inference.py`
- Create: `ChemBlender/scripts/benchmark_topology.py`

**Interfaces:**
- Produces: `infer_distance_topology(structure, settings) -> ImportBatch`.

- [ ] **Step 1: Define settings**

```python
@dataclass(frozen=True, slots=True)
class TopologyInferenceSettings:
    covalent_scale: float = 1.15
    tolerance_angstrom: float = 0.20
    minimum_distance_angstrom: float = 0.25
    max_coordination_default: int = 8
    metal_mode: str = "coordination"
    periodic: bool = False
```

Validate finite positive values and supported mode.

- [ ] **Step 2: Write chemistry and edge-case tests**

Water, benzene, disconnected fragments, close duplicate atoms, metal complex and 50k generated grid. Assert duplicates yield Invalid diagnostic, metal bonds are coordination/ambiguous and no duplicate edges.

- [ ] **Step 3: Implement spatial cell list**

Convert coordinates to angstrom. Bin by the maximum possible cutoff. Inspect 27 neighboring bins. Apply pair cutoff and coordination constraints deterministically. Sort edges lexicographically.

- [ ] **Step 4: Add provenance and benchmark**

Return a derived TopologyRecord with all settings and source structure revision. Benchmark confirms subquadratic behavior and records median/p95.

- [ ] **Step 5: Run and commit**

Commit inference and benchmark.

### Task 3: Implement periodic topology inference

**Files:**
- Create: `ChemBlender/core/topology/periodic.py`
- Create: `tests/test_periodic_topology_inference.py`

**Interfaces:**
- Produces: `infer_periodic_topology()` with lattice shifts per connection.

- [ ] **Step 1: Extend topology data for image shifts**

Add optional `bond_lattice_shifts` with dims `(bond,xyz)` integer dimensionless. Nonperiodic records use zeros or None by contract.

- [ ] **Step 2: Write boundary tests**

Atoms near opposite cell faces connect with a nonzero lattice shift. Nonorthogonal cells use fractional minimum images. Partial PBC honors axis flags.

- [ ] **Step 3: Implement fractional neighbor logic**

Use inverse cell to map displacement, wrap only PBC axes and recover Cartesian distance. Store the chosen integer shift. Detect singular cell through existing Structure validation.

- [ ] **Step 4: Run and commit**

Run periodic and nonperiodic inference tests; commit.

### Task 4: Build topology-aware StructureViewBuilder

**Files:**
- Create: `ChemBlender/views/structure.py`
- Modify: `ChemBlender/dataset_view.py`
- Modify: `ChemBlender/node.py`
- Create: `tests/test_structure_view_contract.py`
- Modify: `tests/blender_smoke.py`

**Interfaces:**
- Produces: `create_structure_view(structure, topology=None, settings=None)` under the new views package and a legacy re-export.

- [ ] **Step 1: Define the view contract**

Mesh contains vertices and topology edges. Named attributes:

```text
atomic_num            POINT INT
cbq_atom_id           POINT INT
bond_order             EDGE INT/FLOAT according to existing GN contract
cbq_bond_id           EDGE INT
cbq_topology_source    object metadata
```

Object stores structure/topology IDs/revisions, quality and display coordinate unit.

- [ ] **Step 2: Write Blender smoke for explicit topology**

Create water with two edges. Assert mesh edges, attributes and existing ball-and-stick node modifier render atoms/bonds.

- [ ] **Step 3: Handle no topology**

Atoms-only view remains valid. UI can request inference. Do not silently infer inside the builder.

- [ ] **Step 4: Integrate periodic image bonds**

The primary mesh keeps canonical cell atoms. Periodic image/edge display uses Geometry Nodes or derived display geometry based on lattice shifts, not duplicated scientific atoms.

- [ ] **Step 5: Preserve existing dataset adapters**

Atomic scalar/vector/selection functions continue to work with the new view. `dataset_view.create_structure_view` re-exports and emits a deprecation warning only in developer logs, not user popups.

- [ ] **Step 6: Run and commit**

Run Blender smoke, view contract and all dataset adapter tests; commit.

### Task 5: Add topology selection and confirmation UI

**Files:**
- Create: `ChemBlender/ui/topology.py`
- Modify: `ChemBlender/ui/project_browser/panel.py`
- Modify: `ChemBlender/ui/properties.py`
- Modify: `tests/blender_smoke.py`

**Interfaces:**
- Produces: topology list, inference settings, Accept/Reject/Recompute and active-view topology switch.

- [ ] **Step 1: Project Browser rows**

Each topology displays source, quality, edge count, inference parameters and view usage.

- [ ] **Step 2: Implement compute/accept/reject operators**

Compute creates a derived proposal. Accept creates a user-confirmed revision or marks selection in ViewRecord; Reject keeps proposal history but removes it from default suggestions.

- [ ] **Step 3: Update view without data mutation**

Switching topology rebuilds or updates mesh edges and render identity. Structure and old topology remain unchanged.

- [ ] **Step 4: Verify and commit**

Blender smoke imports XYZ, infers topology, accepts it, switches to atoms-only and reopens project with identities preserved.

### Task 6: Implement scientific edit preview and derived structures

**Files:**
- Create: `ChemBlender/core/edits/structure.py`
- Create: `ChemBlender/ui/scientific_edit.py`
- Create: `tests/test_structure_derivation.py`
- Modify: `tests/blender_smoke.py`

**Interfaces:**
- Produces: `preview_structure_edits()`, `commit_structure_edits()` and `CHEMBLENDER_OT_apply_scientific_edits`.

- [ ] **Step 1: Write diff tests**

Compare a View Mesh to source Structure/Topology and report coordinate, element, atom count, bond and cell changes. Object matrix transforms are inverted and ignored as scientific edits.

- [ ] **Step 2: Implement derived batch**

Create new Structure and optional TopologyRecord, provenance parent IDs and a diagnostic that source-linked results were not inherited. No source entity mutation.

- [ ] **Step 3: Implement preview UI**

Show counts and maximum displacement, affected result datasets and export choice. Cancel changes nothing.

- [ ] **Step 4: Verify and commit**

Blender smoke moves an atom, creates derived structure, confirms source coordinates and grid bindings unchanged, then exports derived XYZ.
