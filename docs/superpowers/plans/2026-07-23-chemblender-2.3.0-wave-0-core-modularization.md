# ChemBlender 2.3.0 Wave 0 Core Modularization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the monolithic semantic model safely, establish an explicit serialization registry, and preserve all existing public imports and `.cbq` v0.1 reads.

**Architecture:** Convert `ChemBlender/core/model.py` into a package in controlled commits. Sidecar serialization uses an explicit registry keyed by stable type tags rather than scanning class `__module__`. `ChemBlender.core` remains the public compatibility façade.

**Tech Stack:** Python 3.13, dataclasses, `unittest`, NumPy only inside model validation methods, existing `.cbq` NPY sidecar.

## Global Constraints

- `import ChemBlender.core` must not load `bpy`.
- No public constructor field, enum value or serialized type tag changes in this plan.
- Existing `.cbq` v0.1 fixtures must reopen after every task.
- Do not add third-party dependencies.
- Update `.agents/reference/code-architecture-guide.md` with every source responsibility change.
- Use focused commits; no reader or UI feature changes.

---

### Task 1: Lock the public model and serialization surface

**Files:**
- Create: `tests/test_model_public_surface.py`
- Create: `tests/fixtures/sidecar/model-v01/README.md`
- Create: `tests/fixtures/sidecar/model-v01/manifest.json`
- Create: content-addressed NPY fixture under `tests/fixtures/sidecar/model-v01/arrays/` using the generator-produced SHA-256 filename
- Modify: `tests/test_sidecar.py`

**Interfaces:**
- Consumes: current `ChemBlender.core` and sidecar implementation.
- Produces: a frozen list of public model names and a committed v0.1 read fixture.

- [ ] **Step 1: Write the public-surface test**

```python
import unittest

import ChemBlender.core as core


PUBLIC_MODEL_NAMES = {
    "ArrayData", "AtomicProperty", "BandStructure", "BasisSet",
    "CalculationRecord", "CJSONEnvelope", "CIFEnvelope", "DensityMatrix",
    "DensityOfStates", "ExcitedStateSet", "FrameSet", "FermiSurfaceMesh",
    "Grid3D", "ImportBatch", "MolecularTopology", "OrbitalSet",
    "ParserIssue", "ParserReport", "PeriodicSiteData", "PhononModeSet",
    "PropertyDataset", "ProvenanceRecord", "QCProject", "QCSchemaEnvelope",
    "Spectrum", "Structure", "SymmetryResult", "TopologyGraph",
    "VibrationalModeSet",
}


class ModelPublicSurfaceTests(unittest.TestCase):
    def test_public_model_names_remain_importable(self):
        missing = sorted(name for name in PUBLIC_MODEL_NAMES if not hasattr(core, name))
        self.assertEqual(missing, [])
```

- [ ] **Step 2: Generate and commit a deterministic v0.1 sidecar fixture**

Use an existing test helper to create a project containing Structure, MolecularTopology, AtomicProperty, FrameSet, Grid3D and ProvenanceRecord. Save it with the current code before refactoring. Record the generating commit and SHA-256 in `README.md`.

- [ ] **Step 3: Add a fixture reopen test**

```python
def test_committed_v01_fixture_opens(self):
    project = open_project(FIXTURES / "sidecar" / "model-v01")
    self.assertEqual(project.schema_version, "0.1")
    self.assertEqual(len(project.structures), 1)
    self.assertGreaterEqual(len(project.datasets), 3)
    close_project(project)
```

- [ ] **Step 4: Run and commit**

```powershell
& $pythonBin -m unittest tests.test_model_public_surface tests.test_sidecar -v
```

Expected: PASS on the pre-refactor code.

```bash
git add tests
git commit -m "test: lock quantum model and sidecar surface"
```

### Task 2: Replace sidecar module scanning with an explicit type registry

**Files:**
- Create: `ChemBlender/core/model_registry.py`
- Modify: `ChemBlender/core/sidecar.py`
- Create: `tests/test_model_registry.py`

**Interfaces:**
- Consumes: existing model classes and enums.
- Produces: `MODEL_TYPES`, `MODEL_ENUMS`, `model_type_tag()` and `model_type_from_tag()`.

- [ ] **Step 1: Write failing registry tests**

```python
import unittest
from ChemBlender.core import Structure
from ChemBlender.core.model_registry import model_type_from_tag, model_type_tag


class ModelRegistryTests(unittest.TestCase):
    def test_structure_tag_is_stable(self):
        self.assertEqual(model_type_tag(Structure), "Structure")
        self.assertIs(model_type_from_tag("Structure"), Structure)

    def test_unknown_tag_is_rejected(self):
        with self.assertRaises(KeyError):
            model_type_from_tag("UnregisteredType")
```

- [ ] **Step 2: Verify failure**

```powershell
& $pythonBin -m unittest tests.test_model_registry -v
```

Expected: import failure because `model_registry.py` does not exist.

- [ ] **Step 3: Implement an explicit registry**

`model_registry.py` defines immutable mappings. Register every dataclass and enum currently serialized by sidecar. Use class names as existing tags:

```python
from types import MappingProxyType
from . import model

_MODEL_TYPE_NAMES = (
    "ArrayData", "CIFEnvelope", "QCSchemaEnvelope", "CJSONEnvelope",
    "PeriodicSiteData", "MolecularTopology", "Structure", "SymmetryResult",
    "CalculationMetadata", "CalculationRecord", "PropertyDataset",
    "AtomicProperty", "FrameSet", "VibrationalModeSet", "ExcitationContribution",
    "ExcitedStateReferences", "ExcitedStateSet", "Spectrum", "BandPathBranch",
    "BandStructure", "DensityOfStates", "PhononModeSet", "SurfaceProperty",
    "FermiSurfaceMesh", "TopologyConnection", "TopologyPath", "TopologyGraph",
    "BasisShell", "BasisConvention", "BasisSet", "OrbitalChannel", "OrbitalSet",
    "DensityMatrix", "Grid3D", "ProvenanceRecord", "ParserIssue", "ParserReport",
    "ImportBatch", "QCProject",
)

MODEL_TYPES = MappingProxyType({name: getattr(model, name) for name in _MODEL_TYPE_NAMES})
MODEL_ENUMS = MappingProxyType({
    name: getattr(model, name)
    for name in (
        "CalculationStatus", "DatasetStatus", "IssueKind", "BasisFunctionKind",
        "OrbitalKind", "DensityMatrixLevel", "DensityMatrixSpin", "SpectrumKind",
        "SpectrumProfile", "SpinChannel", "EnergyReference", "CriticalPointKind",
    )
})

def model_type_tag(value):
    cls = value if isinstance(value, type) else type(value)
    for tag, registered in MODEL_TYPES.items():
        if registered is cls:
            return tag
    raise TypeError(f"unregistered model type: {cls.__name__}")

def model_type_from_tag(tag):
    return MODEL_TYPES[tag]
```

- [ ] **Step 4: Modify sidecar encoder/decoder**

Remove `_model_registry()` and `_MODEL_CLASSES/_MODEL_ENUMS` scanning. Import the explicit mappings. Encode dataclasses only when their exact type is registered. Decode by exact tag.

- [ ] **Step 5: Run tests and commit**

```powershell
& $pythonBin -m unittest tests.test_model_registry tests.test_sidecar tests.test_model_public_surface -v
```

Expected: all PASS, including the committed v0.1 fixture.

```bash
git add ChemBlender/core/model_registry.py ChemBlender/core/sidecar.py tests
git commit -m "refactor: register sidecar model types explicitly"
```

### Task 3: Convert `model.py` into a package without changing definitions

**Files:**
- Move: `ChemBlender/core/model.py` → `ChemBlender/core/model/__init__.py`
- Modify: `ChemBlender/core/model_registry.py`
- Modify: `.agents/reference/code-architecture-guide.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Consumes: explicit model registry.
- Produces: package path `ChemBlender.core.model` with identical public names.

- [ ] **Step 1: Move the file atomically**

```bash
mkdir -p ChemBlender/core/model
git mv ChemBlender/core/model.py ChemBlender/core/model/__init__.py
```

Do not edit class definitions in this step.

- [ ] **Step 2: Update architecture documentation**

Replace the documented `ChemBlender/core/model.py` responsibility with `ChemBlender/core/model/__init__.py` and state that it is a temporary monolithic package entry before extraction.

- [ ] **Step 3: Run full relevant tests**

```powershell
& $pythonBin -m unittest tests.test_quantum_core tests.test_model_public_surface tests.test_model_registry tests.test_sidecar tests.test_quantum_visualization_docs -v
& $pythonBin -m compileall -q ChemBlender tests
```

Expected: PASS with no public import or sidecar change.

- [ ] **Step 4: Commit**

```bash
git add ChemBlender/core/model .agents/reference/code-architecture-guide.md tests/test_quantum_visualization_docs.py
git commit -m "refactor: convert quantum model into a package"
```

### Task 4: Extract foundational model modules

**Files:**
- Create: `ChemBlender/core/model/common.py`
- Create: `ChemBlender/core/model/arrays.py`
- Create: `ChemBlender/core/model/diagnostics.py`
- Modify: `ChemBlender/core/model/__init__.py`
- Modify: `ChemBlender/core/model_registry.py`
- Modify: tests importing internal helpers only if necessary.

**Interfaces:**
- Produces: foundational validation helpers, enums, ArrayData, ParserIssue and ParserReport re-exported unchanged.

- [ ] **Step 1: Add module-origin tests**

```python
def test_foundational_types_are_split_but_publicly_reexported(self):
    from ChemBlender.core import ArrayData, ParserReport
    self.assertEqual(ArrayData.__module__, "ChemBlender.core.model.arrays")
    self.assertEqual(ParserReport.__module__, "ChemBlender.core.model.diagnostics")
```

- [ ] **Step 2: Verify failure**

Run the single test; expect current module to be `ChemBlender.core.model`.

- [ ] **Step 3: Move definitions unchanged**

Move token validators and shared enum helpers to `common.py`; move `ArrayData` to `arrays.py`; move parser issue/report types to `diagnostics.py`. Import and expose them from `model/__init__.py`. Do not duplicate definitions.

- [ ] **Step 4: Update registry and run tests**

The explicit registry imports public types from `model`, so stable tags remain class names. Run core, sidecar and all adapter tests that instantiate these types.

- [ ] **Step 5: Commit**

```bash
git add ChemBlender/core/model ChemBlender/core/model_registry.py tests .agents/reference/code-architecture-guide.md
git commit -m "refactor: split foundational quantum model types"
```

### Task 5: Extract domain model modules

**Files:**
- Create: `ChemBlender/core/model/structure.py`
- Create: `ChemBlender/core/model/properties.py`
- Create: `ChemBlender/core/model/grids.py`
- Create: `ChemBlender/core/model/spectroscopy.py`
- Create: `ChemBlender/core/model/wavefunction.py`
- Create: `ChemBlender/core/model/periodic.py`
- Create: `ChemBlender/core/model/topology.py`
- Create: `ChemBlender/core/model/project.py`
- Modify: `ChemBlender/core/model/__init__.py`
- Modify: `.agents/reference/code-architecture-guide.md`

**Interfaces:**
- Consumes: foundational model modules.
- Produces: the same public model constructors, validation behavior and type tags in focused modules.

- [ ] **Step 1: Add a module responsibility assertion table**

Create `tests/test_model_modules.py` with expected `__module__` values for representative types:

```python
EXPECTED_MODULES = {
    "Structure": "ChemBlender.core.model.structure",
    "PropertyDataset": "ChemBlender.core.model.properties",
    "Grid3D": "ChemBlender.core.model.grids",
    "Spectrum": "ChemBlender.core.model.spectroscopy",
    "BasisSet": "ChemBlender.core.model.wavefunction",
    "BandStructure": "ChemBlender.core.model.periodic",
    "TopologyGraph": "ChemBlender.core.model.topology",
    "QCProject": "ChemBlender.core.model.project",
}
```

- [ ] **Step 2: Move classes by responsibility**

Preserve definition text and validation. Resolve cycles by importing types through narrow modules and using postponed annotations only where runtime `isinstance` is not required. Runtime validation imports must refer to the exact class.

- [ ] **Step 3: Re-export all public names**

`model/__init__.py` explicitly imports each public symbol. No wildcard imports.

- [ ] **Step 4: Run the full CPython suite**

```powershell
& $pythonBin -m unittest discover -s tests -p 'test_*.py' -v
& $pythonBin -m compileall -q ChemBlender tests
```

Expected: all existing non-optional tests PASS; optional integration skip counts do not increase.

- [ ] **Step 5: Run Blender smoke before commit**

Build/install in an isolated profile because `auto_load` imports core and all adapters at this point. Expected: existing lifecycle and adapter smoke PASS.

- [ ] **Step 6: Commit**

```bash
git add ChemBlender/core/model ChemBlender/core/model_registry.py tests .agents/reference/code-architecture-guide.md
git commit -m "refactor: modularize quantum domain models"
```

### Task 6: Stabilize the public façade

**Files:**
- Modify: `ChemBlender/core/__init__.py`
- Create: `tests/test_core_public_api.py`
- Create: `docs/quantum-visualization/2.3.0/public-core-api.md`

**Interfaces:**
- Produces: a documented stable model façade and a separately identified internal adapter surface.

- [ ] **Step 1: Add `__all__` exactness tests**

Assert all existing public names remain and duplicate entries are absent. Assert model names import from `ChemBlender.core` and optional dependencies are not loaded.

- [ ] **Step 2: Group re-exports without changing names**

Keep backward compatibility. Add comments and the API document that classify model/storage/reader/adapter/recipe symbols. Do not yet remove adapter re-exports; mark their stability as internal in documentation, not by breaking imports.

- [ ] **Step 3: Verify and commit**

```powershell
& $pythonBin -m unittest tests.test_core_public_api tests.test_model_public_surface tests.test_sidecar -v
git diff --check
```

```bash
git add ChemBlender/core/__init__.py tests/test_core_public_api.py docs/quantum-visualization/2.3.0/public-core-api.md
git commit -m "docs: define the ChemBlender core public facade"
```
