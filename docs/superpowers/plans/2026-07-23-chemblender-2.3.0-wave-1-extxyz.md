# ChemBlender 2.3.0 Wave 1 Native XYZ and extXYZ Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the limited native XYZ reader with a generic, typed extXYZ implementation that supports trajectories, lattice/cell metadata, frame and atom properties, diagnostics and semantic round-trip export.

**Architecture:** A low-level tokenizer parses one frame at a time. `Properties` descriptors map columns into typed arrays. Known names map to standard semantic roles; unknown names use CategoricalData or numeric PropertyDataset without loss. Large multi-frame arrays stage directly into sidecar-backed arrays.

**Tech Stack:** Python 3.13 standard library, NumPy from Blender runtime, existing model/import pipeline, `unittest`.

## Global Constraints

- No ASE dependency for base extXYZ.
- Existing ordinary XYZ behavior and reader ID compatibility remain.
- Unknown properties are preserved, not dropped.
- String data never uses NumPy object dtype in sidecar.
- Round-trip compares semantic data, not whitespace or key ordering.
- Reader reports every normalization or loss explicitly.

---

### Task 1: Add extXYZ model support for frame-indexed and categorical data

**Files:**
- Create: `ChemBlender/core/model/categorical.py`
- Modify: `ChemBlender/core/model/properties.py`
- Modify: `ChemBlender/core/model/project.py`
- Modify: `ChemBlender/core/model/__init__.py`
- Modify: `ChemBlender/core/model_registry.py`
- Create: `tests/test_frame_properties.py`

**Interfaces:**
- Produces: `CategoricalData`, `FrameProperty`, `AtomFrameProperty`, `CellFrameProperty`.

- [ ] **Step 1: Write model validation tests**

```python
def test_categorical_data_round_trips_codes_and_categories(self):
    data = CategoricalData(
        codes=ArrayData(numpy.asarray([0, 1, -1]), ("atom",), "dimensionless"),
        categories=("donor", "acceptor"),
        missing_code=-1,
    )
    self.assertEqual(data.categories[data.codes.values[1]], "acceptor")

def test_atom_frame_property_requires_frame_atom_prefix(self):
    with self.assertRaises(ValueError):
        AtomFrameProperty(
            id=uuid4(), revision="r", semantic_role="force", domain="atom_frame",
            data=ArrayData(numpy.zeros((2, 3)), ("atom", "xyz"), "electron_volt_per_angstrom"),
            status=DatasetStatus.COMPLETE, source_calculation=None, provenance_ids=(),
            frame_set_id=uuid4(),
        )
```

- [ ] **Step 2: Implement models and project validation**

`FrameProperty` requires leading `frame`; `AtomFrameProperty` requires `("frame","atom")`; `CellFrameProperty` requires `("frame","cell_vector","xyz")`. All bind a FrameSet and validate frame/atom counts at project commit.

- [ ] **Step 3: Add sidecar round-trip tests**

Include categorical string values and all three frame property types. Assert no object array is written.

- [ ] **Step 4: Run and commit**

Run model, project and sidecar tests; commit.

### Task 2: Implement extXYZ comment and Properties parser

**Files:**
- Create: `ChemBlender/core/formats/extxyz.py`
- Create: `tests/test_extxyz_syntax.py`
- Create: `tests/fixtures/extxyz/README.md`
- Create: `tests/fixtures/extxyz/properties-mixed.extxyz`
- Create: `tests/fixtures/extxyz/multiframe-cell.extxyz`
- Create: `tests/fixtures/extxyz/invalid-property.extxyz`

**Interfaces:**
- Produces: `parse_extxyz_comment()`, `parse_properties_descriptor()`, `iter_extxyz_frames()`.

- [ ] **Step 1: Write descriptor tests**

```python
def test_properties_descriptor_parses_mixed_types(self):
    fields = parse_properties_descriptor(
        "species:S:1:pos:R:3:force:R:3:charge:R:1:fixed:L:1:group:I:1"
    )
    self.assertEqual(
        [(f.name, f.kind, f.columns) for f in fields],
        [("species", "S", 1), ("pos", "R", 3), ("force", "R", 3),
         ("charge", "R", 1), ("fixed", "L", 1), ("group", "I", 1)],
    )
```

Test duplicate names, invalid types, zero columns and truncated atom rows.

- [ ] **Step 2: Implement a quoted key/value tokenizer**

Support `key=value`, quoted values containing spaces and escaped quote handling defined by the extXYZ reference fixtures. Preserve unrecognized metadata as strings. Reject unclosed quotes with a record diagnostic.

- [ ] **Step 3: Implement streaming frames**

Read frame count, raw comment and exactly N atom lines. Parse columns according to Properties. If Properties is absent, use ordinary `species:S:1:pos:R:3`. Do not load all frames in this low-level iterator.

- [ ] **Step 4: Run and commit**

Run syntax and ordinary XYZ regression tests; commit parser primitives.

### Task 3: Map extXYZ frames to project entities

**Files:**
- Modify: `ChemBlender/core/formats/extxyz.py`
- Modify: `ChemBlender/core/reader_catalog.py`
- Modify: `ChemBlender/core/xyz.py`
- Create: `tests/test_extxyz_reader.py`
- Modify: `docs/quantum-visualization/reader-capability-matrix.json`

**Interfaces:**
- Produces: built-in reader ID `extxyz`, version `1`, and ordinary XYZ delegation that avoids ambiguity.

- [ ] **Step 1: Write reader-selection tests**

Ordinary `water.xyz` selects `xyz`; a `.xyz` file with valid `Properties=` selects `extxyz` with higher EXACT match; malformed text selects neither or produces a precise diagnostic only after an explicit override.

- [ ] **Step 2: Map known properties**

Mapping table:

```python
KNOWN_ATOM_PROPERTIES = {
    "force": ("atomic_force", "electron_volt_per_angstrom"),
    "forces": ("atomic_force", "electron_volt_per_angstrom"),
    "vel": ("atomic_velocity", "angstrom_per_femtosecond"),
    "velocity": ("atomic_velocity", "angstrom_per_femtosecond"),
    "charge": ("atomic_charge", "elementary_charge"),
    "mass": ("atomic_mass", "atomic_mass_unit"),
}
```

Units not declared by extXYZ are source-convention assumptions and must produce diagnostics unless metadata supplies a recognized unit key. Unknown R/I/L properties remain typed with `unknown` semantic unit rules and appropriate quality status.

- [ ] **Step 3: Map frame metadata**

`Lattice` is 9 floats row-major, `pbc` accepts T/F tokens, energy/free_energy/time/temperature/step become frame properties, stress/virial accept 9 or 6 components with recorded convention.

- [ ] **Step 4: Handle changing cell and properties**

Compatible frames form one FrameSet. Changing cell becomes CellFrameProperty. A property absent in some frames becomes Partial with a validity mask rather than zero-filled Complete data. Incompatible atom identity splits the source into separate structures and diagnostics.

- [ ] **Step 5: Run and commit**

Run reader, catalog, capability document, sidecar and import preview tests. Commit.

### Task 4: Implement native XYZ/extXYZ exporters

**Files:**
- Create: `ChemBlender/core/exporters/xyz.py`
- Create: `ChemBlender/core/exporters/__init__.py`
- Create: `tests/test_xyz_exporter.py`
- Create: `tests/test_extxyz_roundtrip.py`

**Interfaces:**
- Produces: `export_xyz()`, `export_extxyz()` and `ExportReport` entries.

- [ ] **Step 1: Write ordinary XYZ export test**

Export a Structure and assert count, title, symbols, fixed finite coordinates and newline. Reject unsupported coordinate units rather than silently writing.

- [ ] **Step 2: Write extXYZ schema test**

Create a structure/frame set with numeric, bool and categorical properties. Assert deterministic `Properties` ordering: identity/position first, then standardized roles, then unknown properties by original order key.

- [ ] **Step 3: Implement quoting and categorical export**

Write categories as original strings. Metadata values requiring spaces are quoted. Non-finite values require Partial export confirmation and an explicit missing-value token policy in ExportReport.

- [ ] **Step 4: Implement semantic round-trip comparator**

Parse exported file and compare atomic numbers, coordinates, cell, PBC, dims, categories and valid masks with tolerances. Do not compare UUIDs or provenance IDs.

- [ ] **Step 5: Run and commit**

Run round-trip tests including multi-frame cell and unknown properties; commit.

### Task 5: Add extXYZ import/export UI and performance paths

**Files:**
- Modify: `ChemBlender/ui/import_preview.py`
- Modify: `ChemBlender/ui/project_browser/panel.py`
- Create: `ChemBlender/ui/export.py`
- Modify: `tests/blender_smoke.py`
- Create: `ChemBlender/scripts/benchmark_extxyz.py`

**Interfaces:**
- Produces: property summary, frame controls and export operator.

- [ ] **Step 1: Show extXYZ capabilities in Preview**

Display frame count, atom properties, frame properties, lattice/PBC and any assumed-unit diagnostics.

- [ ] **Step 2: Add data browser groups**

FrameSet and its related properties appear together. Selecting atomic force can apply vector arrows to the active structure view.

- [ ] **Step 3: Add exporter action**

Export selected Structure or FrameSet with a loss preview. Partial/Ambiguous requires confirmation.

- [ ] **Step 4: Benchmark**

Generate deterministic 1k-frame/1k-atom and larger metadata-only cases. Measure first preview, parse, sidecar write, frame access and export. Ensure large paths do not construct nested Python tuples for all values.

- [ ] **Step 5: Verify and commit**

Run Blender smoke with multi-frame extXYZ, save/reopen and force-vector view; run benchmark and document baseline.
