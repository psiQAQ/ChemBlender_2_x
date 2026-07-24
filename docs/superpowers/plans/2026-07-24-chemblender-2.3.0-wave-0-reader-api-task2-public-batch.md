# ChemBlender 2.3.0 Wave 0 Reader API Task 2 Public Batch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a project-free scientific model façade and a frozen `PublicImportBatch`, with validated no-copy conversion to and from the existing internal `ImportBatch`.

**Architecture:** Re-export trusted core model classes as exact aliases through the installed Reader API namespace. Keep the public batch as a strict tuple container with exact-type allowlists. Conversion is a thin wrapper: internal-to-public preserves entity and array identity; public-to-internal constructs the existing `ImportBatch` and delegates all graph validation to an isolated `QCProject.commit()`.

**Tech Stack:** Python 3.13 standard library (`dataclasses`, `uuid`, `unittest`), existing ChemBlender core model/XYZ/Cube readers, and NumPy objects already carried by the model.

## Global Constraints

- Work only on `feat/2.3.0-wave0-platform-foundation`.
- Starting checkpoint is `ca06235ff01514ecbf56e19725ac970095c7a46f`.
- All `ChemBlender/reader_api/` imports are relative; never hardcode `ChemBlender` or `bl_ext`.
- Expose trusted scientific constructors as exact aliases; do not copy, wrap, or subclass them.
- `PublicImportBatch` is not an internal `ImportBatch` subclass and never owns a `QCProject`, Blender value, callable, or mutation method.
- Use exact-type allowlists at the public boundary; reject unknown subclasses.
- Do not deep-copy entities, `ArrayData`, NumPy arrays, or lazy arrays.
- Public-to-internal conversion must use the existing `QCProject.commit()` validation path and expose stable public conversion exceptions.
- Do not use pickle, class `__module__` identity, dynamic import, or new dependencies.
- Do not create `ChemBlender/reader_api/canonical_document.py` or begin Reader API Task 3, worker bridge, Registration/UI, or Wave 1–4.
- Use one implementation commit and a separate completion checkpoint.
- Do not push without a new explicit user authorization.

---

### Task 1: Public scientific model aliases

**Files:**
- Create: `ChemBlender/reader_api/public_model.py`
- Modify: `ChemBlender/reader_api/__init__.py`
- Test: `tests/test_public_import_batch.py`
- Modify: `tests/test_reader_plugin_manifest.py`

**Interfaces:**
- Re-export exact trusted entity and enum classes through `ChemBlender.reader_api`.
- Exclude `QCProject`, internal `ImportBatch`, `CalculationGroup`, Blender types, and mutable registries.
- Approved entities:
  `ArrayData`, `SourceRecord`, `SourceRevision`, `CIFEnvelope`,
  `QCSchemaEnvelope`, `CJSONEnvelope`, `PeriodicSiteData`,
  `MolecularTopology`, `Structure`, `SymmetryResult`,
  `CalculationMetadata`, `CalculationRecord`, `PropertyDataset`,
  `AtomicProperty`, `FrameSet`, `Grid3D`, `VibrationalModeSet`,
  `ExcitedStateSet`, `Spectrum`, `BandStructure`, `DensityOfStates`,
  `PhononModeSet`, `FermiSurfaceMesh`, `TopologyGraph`,
  `ExcitationContribution`, `ExcitedStateReferences`, `BandPathBranch`,
  `SurfaceProperty`, `TopologyConnection`, `TopologyPath`, `BasisShell`,
  `BasisConvention`, `BasisSet`, `OrbitalChannel`, `OrbitalSet`,
  `DensityMatrix`, `ProvenanceRecord`, `ParserIssue`, `ParserReport`,
  `DiagnosticValue`, and `ImportDiagnostic`.
- Approved enums:
  `CalculationStatus`, `DatasetStatus`, `IssueKind`, `BasisFunctionKind`,
  `OrbitalKind`, `DensityMatrixLevel`, `DensityMatrixSpin`, `SpectrumKind`,
  `SpectrumProfile`, `SpinChannel`, `EnergyReference`, `CriticalPointKind`,
  `QualityStatus`, and `DiagnosticSeverity`.

- [ ] **Step 1: Write failing public-surface tests**

Assert representative identities:

```python
reader_api.Structure is ChemBlender.core.Structure
reader_api.Grid3D is ChemBlender.core.Grid3D
reader_api.ParserReport is ChemBlender.core.ParserReport
```

Assert `QCProject` and `ImportBatch` are absent, and update the exact
`reader_api.__all__` contract.

- [ ] **Step 2: Implement exact relative aliases**

Expose the approved scientific types and enums from `..core`. Keep any
exact-type collections private and immutable.

---

### Task 2: PublicImportBatch contract

**Files:**
- Create: `ChemBlender/reader_api/public_model.py`
- Test: `tests/test_public_import_batch.py`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True, eq=False, repr=False)
class PublicImportBatch:
    sources: tuple[SourceRecord, ...] = ()
    source_revisions: tuple[SourceRevision, ...] = ()
    structures: tuple[Structure, ...] = ()
    cif_envelopes: tuple[CIFEnvelope, ...] = ()
    qcschema_envelopes: tuple[QCSchemaEnvelope, ...] = ()
    cjson_envelopes: tuple[CJSONEnvelope, ...] = ()
    symmetry_results: tuple[SymmetryResult, ...] = ()
    calculations: tuple[CalculationRecord, ...] = ()
    datasets: tuple[PropertyDataset | Grid3D, ...] = ()
    basis_sets: tuple[BasisSet, ...] = ()
    orbital_sets: tuple[OrbitalSet, ...] = ()
    density_matrices: tuple[DensityMatrix, ...] = ()
    provenance: tuple[ProvenanceRecord, ...] = ()
    report: ParserReport | None = None
    diagnostics: tuple[ImportDiagnostic, ...] = ()
```

- [ ] **Step 1: Write failing container tests**

Cover frozen/slots behavior, mutable sequence isolation, exact trusted types,
the exact approved dataset types (`PropertyDataset`, `AtomicProperty`,
`FrameSet`, `Grid3D`, `VibrationalModeSet`, `ExcitedStateSet`, `Spectrum`,
`BandStructure`, `DensityOfStates`, `PhononModeSet`, `FermiSurfaceMesh`, and
`TopologyGraph`), exact `ParserReport`, unknown subclass rejection, no
automatic NumPy equality, and absence of project mutation methods.

- [ ] **Step 2: Implement the minimum strict container**

Normalize each collection to a tuple, validate exact types against private
allowlists, and retain entity/array identity. Do not deep-copy.

---

### Task 3: Built-in conversion bridge

**Files:**
- Create: `ChemBlender/reader_api/builtin_bridge.py`
- Modify: `ChemBlender/reader_api/__init__.py`
- Test: `tests/test_public_import_batch.py`

**Interfaces:**

```python
class PublicBatchError(Exception): ...
class PublicBatchValidationError(PublicBatchError): ...

def public_batch_from_internal(batch) -> PublicImportBatch: ...
def internal_batch_from_public(batch) -> ImportBatch: ...
```

- [ ] **Step 1: Write failing conversion-boundary tests**

Require exact input container types, reject untrusted entity subclasses, keep
inputs unchanged, preserve entity and array identity, and convert internal
validation errors into `PublicBatchValidationError`.

- [ ] **Step 2: Implement thin conversion**

`public_batch_from_internal()` creates a new public wrapper from the existing
tuples. `internal_batch_from_public()` creates a new internal `ImportBatch`,
then validates it with:

```python
QCProject(uuid4(), CURRENT_PROJECT_SCHEMA_VERSION).commit(candidate)
```

Catch internal `TypeError`, `ValueError`, or `KeyError` at this public
boundary. Never return the temporary project or close shared lazy arrays.

---

### Task 4: Real XYZ and Cube round-trip

**Files:**
- Test: `tests/test_public_import_batch.py`
- Fixture: `tests/fixtures/xyz/water.xyz`
- Fixture: `tests/fixtures/cube/sheared.cube`

- [ ] **Step 1: Add real-reader round trips**

For XYZ, preserve IDs, revisions, dims, units, values, provenance and report
issues through internal → public → internal. For Cube, preserve the structure,
all `Grid3D` datasets, origin, step vectors, coordinate unit and values.

- [ ] **Step 2: Add graph-integrity failures**

Prove dangling structure references and mismatched
`ParserReport.created_entity_ids` fail as `PublicBatchValidationError`.

---

### Task 5: Public surface, namespace and architecture contracts

**Files:**
- Modify: `ChemBlender/reader_api/__init__.py`
- Modify: `tests/test_reader_plugin_manifest.py`
- Modify: `.agents/reference/code-architecture-guide.md`
- Test: `tests/test_quantum_visualization_docs.py`
- Test: `tests/test_public_import_batch.py`

- [ ] **Step 1: Update architecture responsibilities**

Document `public_model.py` as the controlled scientific façade and
`builtin_bridge.py` as the validating, no-copy conversion boundary. State
that plugins cannot obtain `QCProject`.

- [ ] **Step 2: Verify namespace safety**

Assert the two new modules contain no absolute `ChemBlender`/`bl_ext` imports,
work under a synthetic installed package namespace, and do not load `bpy`,
`cclib`, `iodata`, `gbasis`, `ase`, or `pymatgen`.

- [ ] **Step 3: Run RED before production edits**

```powershell
& $pythonBin -m unittest tests.test_public_import_batch -v
```

Expected: `ModuleNotFoundError` or missing public names because Task 2 source
does not exist.

---

### Task 6: Full regression and checkpoint

**Files:**
- Modify: `.agents/active/2.3.0-wave-0-platform-foundation.md`
- Modify: `docs/superpowers/plans/2026-07-24-chemblender-2.3.0-wave-0-reader-api-task2-public-batch.md`

- [ ] **Step 1: Run focused GREEN**

```powershell
& $pythonBin -m unittest `
  tests.test_public_import_batch `
  tests.test_reader_plugin_manifest `
  tests.test_quantum_readers `
  tests.test_xyz_reader `
  tests.test_cube_reader `
  tests.test_quantum_visualization_docs -v
```

- [ ] **Step 2: Commit implementation**

```powershell
git add `
  ChemBlender/reader_api/public_model.py `
  ChemBlender/reader_api/builtin_bridge.py `
  ChemBlender/reader_api/__init__.py `
  tests/test_public_import_batch.py `
  tests/test_reader_plugin_manifest.py `
  .agents/reference/code-architecture-guide.md
git commit -m "feat: add reader API public import batches"
```

- [ ] **Step 3: Complete independent reviews**

Run one task-scoped specification/code-quality review and one independent
broad review. Fix all Critical/Important and directly related Minor findings,
then rerun affected review and verification.

- [ ] **Step 4: Run fresh full verification**

```powershell
& $pythonBin -m unittest discover -s tests -p "test_*.py" -v
& $pythonBin -m compileall -q ChemBlender worker tests
& $pythonBin -c "import sys; import ChemBlender.reader_api as api; assert not hasattr(api, 'QCProject'); assert not hasattr(api, 'ImportBatch'); assert not any(name in sys.modules for name in ('bpy','cclib','iodata','gbasis','ase','pymatgen'))"
git diff --check
git status --short
```

Blender validate/build/smoke is:
`Not Run: no registration or Blender runtime code changed`.

- [ ] **Step 5: Commit completed checkpoint**

Record planning and implementation SHAs, RED/GREEN evidence, full test counts,
XYZ/Cube round trips, array no-copy, synthetic namespace, review results,
Blender `Not Run`, the Task 3 stop boundary, and no-push policy. Then commit:

```powershell
git add .agents/active/2.3.0-wave-0-platform-foundation.md
git commit -m "chore: checkpoint wave 0 reader API task 2"
```

Confirm `canonical_document.py` remains absent and stop before Reader API
Task 3.
