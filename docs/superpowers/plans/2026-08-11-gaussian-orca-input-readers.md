# Gaussian and ORCA Cartesian Input Readers Implementation Plan

> **Execution mode:** Follow this plan in the current isolated worktree with TDD. Complete each task's red/green verification before its commit.

**Goal:** Add built-in, dependency-free Gaussian `.gjf`/`.com` and ORCA `.inp` Cartesian structure readers that work through ChemBlender Quick Import and are proven in Blender 5.1.

**Architecture:** Two format-specific native reader modules return the existing `ImportBatch`/`Structure` model. The existing reader catalog exposes them to Reader API v1, Quick Import and file handlers. The import pipeline remains authoritative for `SourceRecord` and `SourceRevision`; no execution or calculation parsing is added.

**Tech stack:** Python standard library, ChemBlender semantic core, `unittest`, Blender 5.1 extension runtime, existing documentation generator.

**Design:** `docs/superpowers/specs/2026-08-11-gaussian-orca-input-readers-design.md`

---

## Task 1: Add Gaussian reader tests and fixture

**Files:**

- Create: `tests/fixtures/gaussian/water.gjf`
- Create: `tests/test_gaussian_input_reader.py`

### Step 1: Write the failing golden-path tests

Cover:

- complete `.gjf` sniff returns `EXACT`;
- content selection works when the fixture is copied to a wrong extension;
- parse produces O/H/H, `(3, 3)` coordinates in angstrom, charge `0`, multiplicity `1`;
- `.com` is declared by the descriptor;
- provenance contains format, coordinate mode, title and a 64-character hash;
- batch commits to `QCProject`.

### Step 2: Write the failing strict-boundary tests

Use temporary byte fixtures for:

- D/T mapping warning;
- non-zero charge and multiplicity;
- missing route/title/charge/coordinates;
- invalid multiplicity, unknown element, `nan` coordinate and extra atom columns;
- Z-matrix, freeze-code and `--Link1--` rejection;
- trailing basis/ECP text after the geometry is accepted without being parsed.

### Step 3: Run the test and prove RED

```powershell
python -m unittest tests.test_gaussian_input_reader -v
```

Expected: fail because `ChemBlender.core.formats.gaussian_input` does not exist.

## Task 2: Implement the Gaussian reader

**Files:**

- Create: `ChemBlender/core/formats/gaussian_input.py`

### Step 1: Implement the smallest parser

Implement only:

- UTF-8-sig decoding;
- strict Link0/route/title/charge-multiplicity/Cartesian section parsing;
- standard element symbols plus D/T warning;
- finite four-column coordinates;
- one `Structure`, provenance and report;
- content sniffing with `EXACT`, `PROBABLE` and `NONE`;
- `GAUSSIAN_INPUT_READER` with `.gjf` and `.com`, `structure = supported`.

Do not add a shared parser framework, route parser, dependency or calculation model.

### Step 2: Run the focused test and prove GREEN

```powershell
python -m unittest tests.test_gaussian_input_reader -v
```

### Step 3: Commit the Gaussian slice

```powershell
git add ChemBlender/core/formats/gaussian_input.py tests/fixtures/gaussian/water.gjf tests/test_gaussian_input_reader.py
git diff --cached --check
git commit -m "feat: read Gaussian Cartesian inputs"
```

## Task 3: Add ORCA reader tests and fixture

**Files:**

- Create: `tests/fixtures/orca/water.inp`
- Create: `tests/test_orca_input_reader.py`

### Step 1: Write the failing golden-path tests

Cover:

- complete inline `* xyz 0 1` sniff returns `EXACT`;
- generic `.inp` without ORCA coordinates returns `NONE`;
- content selection works with a wrong extension;
- parse normalizes the same water structure, charge and multiplicity as Gaussian;
- provenance and `QCProject` commit are complete.

### Step 2: Write the failing strict-boundary tests

Cover:

- D/T warning and non-zero charge/multiplicity;
- `xyzfile` recognized by sniff but rejected by parse with a specific error;
- missing terminator, multiple coordinate blocks, empty block, invalid multiplicity;
- unknown element, `inf` coordinate and extra atom columns.

### Step 3: Run and prove RED

```powershell
python -m unittest tests.test_orca_input_reader -v
```

Expected: fail because `ChemBlender.core.formats.orca_input` does not exist.

## Task 4: Implement the ORCA reader

**Files:**

- Create: `ChemBlender/core/formats/orca_input.py`

### Step 1: Implement the smallest parser

Implement the unique inline `* xyz charge multiplicity` block, strict four-column atoms, finite coordinates, format-specific errors, provenance/report and `ORCA_INPUT_READER`.

Do not resolve `xyzfile`, parse `%coords`, interpret ORCA keywords or accept multiple blocks.

### Step 2: Run focused Gaussian and ORCA tests

```powershell
python -m unittest tests.test_gaussian_input_reader tests.test_orca_input_reader -v
```

### Step 3: Commit the ORCA slice

```powershell
git add ChemBlender/core/formats/orca_input.py tests/fixtures/orca/water.inp tests/test_orca_input_reader.py
git diff --cached --check
git commit -m "feat: read ORCA Cartesian inputs"
```

## Task 5: Register both readers and prove the public path

**Files:**

- Modify: `ChemBlender/core/formats/__init__.py`
- Modify: `ChemBlender/core/__init__.py`
- Modify: `ChemBlender/core/reader_catalog.py`
- Modify: `tests/test_core_public_api.py`
- Modify: `tests/test_reader_catalog.py`
- Modify: `tests/test_reader_api_registry.py`
- Create: `tests/test_quantum_input_import_pipeline.py`

### Step 1: Write failing integration assertions

Assert:

- public exports include both descriptors and parse/sniff functions;
- built-in catalog and Reader API registry contain 21 unique readers;
- both readers have `availability_contract = {"kind": "always"}`;
- registry selects each fixture without ambiguity;
- Quick Import preflight creates a selected-reader preview;
- preview commit stores source revision, structure, charge and multiplicity in `QCProject`;
- file-handler extension projection includes `.gjf`, `.com` and `.inp` through the existing dynamic registry path.

### Step 2: Run and prove RED

```powershell
python -m unittest tests.test_core_public_api tests.test_reader_catalog tests.test_reader_api_registry tests.test_quantum_input_import_pipeline -v
```

### Step 3: Add catalog/public registrations and fixture families

Register the descriptors and fixture families. Do not add optional dependency entries or export capability.

### Step 4: Run and prove GREEN

```powershell
python -m unittest tests.test_gaussian_input_reader tests.test_orca_input_reader tests.test_core_public_api tests.test_reader_catalog tests.test_reader_api_registry tests.test_quantum_input_import_pipeline tests.test_file_handler_contract -v
```

### Step 5: Commit the registry slice

```powershell
git add ChemBlender/core/formats/__init__.py ChemBlender/core/__init__.py ChemBlender/core/reader_catalog.py tests/test_core_public_api.py tests/test_reader_catalog.py tests/test_reader_api_registry.py tests/test_quantum_input_import_pipeline.py
git diff --cached --check
git commit -m "feat: expose quantum input readers"
```

## Task 6: Publish examples, capability documents and architecture

**Files:**

- Create: `examples/user-workflows/inputs/gaussian/water.gjf`
- Create: `examples/user-workflows/inputs/gaussian/water.md`
- Create: `examples/user-workflows/inputs/orca/water.inp`
- Create: `examples/user-workflows/inputs/orca/water.md`
- Modify: `.agents/reference/code-architecture-guide.md`
- Modify: `docs/user/formats.md`
- Modify: `docs/quantum-visualization/reader-capability-matrix.json`
- Modify: `docs/user/format-capabilities.json`
- Modify: `docs/user/dependencies.json`
- Modify: relevant documentation contract tests only where the new public capability requires it

### Step 1: Add representative user examples

Use minimal neutral-singlet water inputs and adjacent Markdown files containing source, license/provenance, expected reader, atom count, charge/multiplicity and strict unsupported boundaries.

### Step 2: Update architecture responsibilities

Add both new source modules to the architecture guide with their public entry points and strict structure-only responsibility.

### Step 3: Regenerate capability documents

```powershell
python ChemBlender/scripts/generate_format_docs.py
python ChemBlender/scripts/generate_format_docs.py --check
```

### Step 4: Run documentation and format contracts

```powershell
python -m unittest tests.test_generated_docs_fresh tests.test_quantum_visualization_docs tests.test_reader_catalog -v
```

### Step 5: Commit the published capability

```powershell
git add .agents/reference/code-architecture-guide.md docs examples/user-workflows/inputs/gaussian examples/user-workflows/inputs/orca
git diff --cached --check
git commit -m "docs: publish Gaussian and ORCA input support"
```

## Task 7: Add Blender runtime acceptance

**Files:**

- Modify: `tests/blender_smoke.py`

### Step 1: Add a focused runtime assertion

Through public `bpy.ops.chemblender.quick_import`:

- stage the Gaussian and ORCA workflow examples;
- inspect preview rows for `gaussian-input` and `orca-input`;
- confirm each import;
- resolve its `SourceRevision` and imported `Structure`;
- assert atom count, charge, multiplicity and coordinates;
- assert a visible mesh View is bound to the imported structure;
- assert Project Browser contains the structure.

Keep the assertion format-specific and do not duplicate the complete generic Quick Import test.

### Step 2: Run static syntax and the narrow test set

```powershell
python -m py_compile tests/blender_smoke.py
python -m unittest tests.test_gaussian_input_reader tests.test_orca_input_reader tests.test_quantum_input_import_pipeline -v
```

### Step 3: Commit runtime acceptance

```powershell
git add tests/blender_smoke.py
git diff --cached --check
git commit -m "test: verify quantum input Quick Import"
```

## Task 8: Full verification and Blender 5.1 proof

### Step 1: Resolve the live Blender toolchain

Run `blender-mcp --help`, then query Blender version, executable, bundled Python, runtime system and extension repositories together. Require Blender 5.1.0 or newer.

### Step 2: Run repository tests with the verified Python

At minimum:

```powershell
python -m unittest tests.test_gaussian_input_reader tests.test_orca_input_reader tests.test_quantum_input_import_pipeline tests.test_reader_catalog tests.test_reader_api_registry tests.test_core_public_api tests.test_file_handler_contract tests.test_generated_docs_fresh tests.test_quantum_visualization_docs -v
python ChemBlender/scripts/generate_format_docs.py --check
python -m unittest discover -s tests -p "test_*.py"
```

### Step 3: Validate and build the extension

Use the repository build entry point with live Blender MCP info. Inspect the resulting ZIP content; do not treat ZIP existence as runtime proof.

### Step 4: Install and run Blender smoke tests

Install through Blender Extensions, verify enabled key `bl_ext.user_default.chemblender`, and run `tests/blender_smoke.py` in Blender 5.1. Capture the public Quick Import assertions for both new formats.

### Step 5: Final review

```powershell
git diff HEAD~5 --check
git status --short --branch
git log --oneline --decorate -8
```

Review the full branch diff for scope, scientific correctness, dependency neutrality, source encoding and accidental generated/runtime artifacts.

### Step 6: Commit any verification-only adjustment separately

Only if verification exposes a required fix: reproduce with a failing test, implement the smallest fix, rerun the affected and full gates, then commit a truthful message.
