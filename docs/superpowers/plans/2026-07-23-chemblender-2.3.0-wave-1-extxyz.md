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
- `FrameProperty` validity mask prefix `("frame",)`.
- `AtomFrameProperty` validity mask prefix `("frame", "atom")`.
- `CellFrameProperty` validity mask prefix `("frame",)`.
- For the required prefix above, every numeric or logical Partial property
  satisfies `mask.dims == required_prefix`,
  `mask.values.shape == data.values.shape[:len(required_prefix)]`,
  `mask.values.dtype == numpy.bool_` and `mask.unit == "dimensionless"`.
  Numeric and logical Partial properties use that boolean mask.
- `CategoricalData` stores integer codes, unique categories and an explicit missing code; it never stores an object-dtype array and does not add a redundant validity mask.

- [x] **Step 1: Write model validation tests**

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

- [x] **Step 2: Implement models and project validation**

`FrameProperty` requires leading `frame`; `AtomFrameProperty` requires
`("frame","atom")`; `CellFrameProperty` requires
`("frame","cell_vector","xyz")`. All bind a FrameSet and validate frame/atom
counts at project commit. Numeric and bool Partial datasets require their
matching validity mask; Complete datasets must not use a mask. Categorical
missing values use only `CategoricalData.missing_code`.

- [x] **Step 3: Add sidecar round-trip tests**

Include categorical string values and all three frame property types. Assert no object array is written.

- [x] **Step 4: Run and commit**

Run model, project and sidecar tests; commit.

### Task 2: Implement extXYZ comment and Properties parser

**Files:**
- Create: `ChemBlender/core/formats/__init__.py`
- Create: `ChemBlender/core/formats/extxyz.py`
- Create: `tests/test_extxyz_syntax.py`
- Create: `tests/fixtures/extxyz/README.md`
- Create: `tests/fixtures/extxyz/properties-mixed.extxyz`
- Create: `tests/fixtures/extxyz/multiframe-cell.extxyz`
- Create: `tests/fixtures/extxyz/invalid-property.extxyz`
- Create: libAtoms, ASE and OVITO common compatibility fixtures under
  `tests/fixtures/extxyz/`; ASE remains fixture provenance only, not a runtime dependency.

**Interfaces:**
- Produces: `parse_extxyz_comment()`, `parse_properties_descriptor()`, `iter_extxyz_frames()`.

- [x] **Step 1: Write descriptor tests**

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

- [x] **Step 2: Implement a quoted key/value tokenizer**

Support `key=value`, quoted values containing spaces and escaped quote handling
defined by the extXYZ reference fixtures. Preserve typed per-config metadata as
string, integer, real, logical, 1-D array and 2-D array values. When a value
cannot be safely typed, retain its raw lexeme and diagnostic instead of silently
coercing it to a string. Reject unclosed quotes with a record diagnostic.

- [x] **Step 3: Implement streaming frames**

Read frame count, raw comment and exactly N atom lines. Parse columns according
to Properties. If Properties is absent, use ordinary
`species:S:1:pos:R:3`. Use a bounded one-frame iterator; do not load all frames
in this low-level iterator.

- [x] **Step 4: Run and commit**

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

`Lattice` is exactly nine floats in the lattice-vector sequence
`ax ay az bx by bz cx cy cz`; do not describe the contract only as row-major or
column-major. PBC defaults are exact:

- no `Lattice` and no `pbc`: `(False, False, False)`;
- `Lattice` and no `pbc`: `(True, True, True)`;
- explicit `pbc` overrides either default and accepts T/F tokens.

energy/free_energy/time/temperature/step become frame properties, while
stress/virial accept 9 or 6 components with a recorded convention.

- [ ] **Step 4: Handle changing cell and properties**

Compatible frames form one FrameSet. Changing cell becomes CellFrameProperty.
A numeric or logical property absent in some frames becomes Partial with the
Task 1 boolean validity mask rather than zero-filled Complete data. A categorical
property uses its integer missing code and does not add a second validity mask.
Incompatible atom identity splits the source into separate structures and
diagnostics.

For large compatible trajectories, stage arrays through a staged memmap/NPY owner
and append from the bounded frame iterator. The mapper must not construct a nested Python tuple containing all frames. Cancellation cleanup removes all owned staging
files, and sidecar publication failure rolls back the staged project without
leaking files or partially committing entities.

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

Create a structure/frame set with numeric, bool and categorical properties.
Assert deterministic `Properties` ordering: identity/position first, then
standardized roles, then unknown properties by original order key. Cover
deterministic typed metadata serialization for scalar, 1-D and 2-D typed metadata,
preserving string/integer/real/logical type and array shape.

- [ ] **Step 3: Implement quoting and categorical export**

Write categories as original strings. Metadata values requiring spaces are
quoted. An unsafe raw lexeme and diagnostic may be emitted unchanged only when
the lexeme remains grammar-safe and its metadata is unmodified; otherwise the
export report presents a loss preview and requires confirmation before omission
or string fallback. Non-finite values require Partial export confirmation and an
explicit missing-value token policy in ExportReport.

- [ ] **Step 4: Implement semantic round-trip comparator**

Parse exported file and compare atomic numbers, coordinates, cell, PBC, dims,
categories, valid masks and metadata type, shape and value with tolerances.
Include scalar, 1-D and 2-D metadata plus the unsafe-lexeme loss path. Do not
compare UUIDs or provenance IDs.

- [ ] **Step 5: Run and commit**

Run round-trip tests including multi-frame cell and unknown properties; commit.

### Task 5: Add extXYZ import/export UI and performance paths

**Files:**
- Modify: `ChemBlender/ui/import_preview.py`
- Modify: `ChemBlender/ui/project_browser/panel.py`
- Create: `ChemBlender/ui/export.py`
- Modify: `ChemBlender/runtime/registration.py`
- Modify: `tests/test_registration_contract.py`
- Modify: `tests/blender_smoke.py`
- Create: `ChemBlender/scripts/benchmark_extxyz.py`
- Modify: `.agents/reference/code-architecture-guide.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Produces: property summary, frame controls and export operator.
- `ChemBlender/ui/export.py` is an explicit registration root; it must not rely
  on another UI module re-exporting its Blender classes.

- [ ] **Step 1: Show extXYZ capabilities in Preview**

Display frame count, atom properties, frame properties, lattice/PBC and any assumed-unit diagnostics.

- [ ] **Step 2: Add data browser groups**

FrameSet and its related properties appear together. Selecting atomic force can apply vector arrows to the active structure view.

- [ ] **Step 3: Add exporter action**

Export selected Structure or FrameSet with a loss preview. Partial/Ambiguous requires confirmation.

- [ ] **Step 4: Benchmark**

Generate deterministic 1k-frame/1k-atom and larger metadata-only cases. Measure first preview, parse, sidecar write, frame access and export. Ensure large paths do not construct nested Python tuples for all values.

The benchmark and Blender smoke also cover cancellation cleanup and publication
rollback for the staged memmap/NPY path.

- [ ] **Step 5: Verify and commit**

Run Blender smoke with multi-frame extXYZ, save/reopen and force-vector view; run benchmark and document baseline.
