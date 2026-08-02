# ChemBlender 2.4.0 Deterministic Native PDB Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development and superpowers:executing-plans task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dependency-free deterministic native PDB core exporter with explicit loss confirmation, atomic destination publication, and Semantic native re-import verification.

**Architecture:** Reuse the frozen `pdb_export_readiness()` contract, existing exchange entities, `ExportReport`, `MolecularExport`, and `atomic_write_chunks`. Add one focused writer module that projects `Structure` + `BiologicalHierarchy` + optional `FrameSet`/occupancy/B-factor into normalized PDB text. The writer never stores parser objects or creates another biological model.

**Tech Stack:** Python 3.13, Blender-bundled NumPy, standard-library `unittest`, native `ChemBlender.core.formats.pdb`, Blender Extensions tooling.

## Global Constraints

- Start only after `.agents/queued/2.4.0-pdb-export.md` is explicitly activated.
- Preserve `Structure`, `BiologicalHierarchy`, `FrameSet`, `AtomicProperty`, Reader API `1.0-rc1`, and sidecar schema 1.0.
- Reuse `pdb_export_readiness()`; do not fork its association or field-budget rules.
- Use only existing dependencies. Importing the exporter must not load `bpy`, RDKit, Gemmi, ASE, Open Babel, cclib, IOData, GBasis, or spglib.
- The normalized slice is **No CONECT** and **No UI**. Do not synthesize topology, `CRYST1`, secondary structure, assemblies, annotations, comments, or raw source records.
- Any omitted scientific/source semantics must appear in a stable loss report and block destination publication until `confirm_loss=True`.
- Do not modify manifest version, CHANGELOG release entries, workflows, tags, or Releases.

---

### Task 1: Activate and freeze the public writer contract

**Files:**
- Move: `.agents/queued/2.4.0-pdb-export.md` to `.agents/active/2.4.0-pdb-export.md`
- Create: `tests/test_pdb_exporter.py`
- Create: `docs/quantum-visualization/2.4.0/pdb-export-contract.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**

```python
preview_pdb_export(project_entities) -> ExportReport

export_pdb(
    project_entities,
    *,
    confirm_loss=False,
    destination=None,
    is_cancelled=None,
) -> MolecularExport
```

- [ ] **Step 1: Activate only this cursor**

Set goal `CB240-PDB-EXPORT-T3`, state `in_progress`, and current task `Task 1 — Freeze native PDB export contract`. Leave PQR, Cube, Reader API stable and PDB UI unstarted.

- [ ] **Step 2: Write contract tests before implementation**

Tests must require:

- `preview_pdb_export` and `export_pdb` are public from `ChemBlender.core.exporters`;
- a ready single-model fixture emits deterministic text and no confirmation;
- a source with `CONECT`, `CRYST1`, raw/source-only records, or unsupported formal-charge semantics reports stable loss entries;
- a report requiring confirmation returns empty text and does not create a destination until `confirm_loss=True`;
- `confirm_loss` is exact `bool`;
- unsupported readiness raises `ValueError` containing the stable readiness tokens.

- [ ] **Step 3: Run RED**

```powershell
$pythonBin = 'C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe'
& $pythonBin -m unittest tests.test_pdb_export_readiness tests.test_pdb_exporter -v
```

Expected: `tests.test_pdb_exporter` fails to import the two writer functions.

---

### Task 2: Implement deterministic fixed-column PDB text

**Files:**
- Create: `ChemBlender/core/exporters/pdb.py`
- Modify: `ChemBlender/core/exporters/__init__.py`
- Modify: `.agents/reference/code-architecture-guide.md`
- Modify: `tests/test_pdb_exporter.py`

**Interfaces:**
- Consumes: Task 1 signatures plus `PDBPQRExportStatus`, `ExportReport`, `ExportReportEntry`, `MolecularExport`, `atomic_write_chunks`, and `ExportCancelled`.
- Produces: normalized UTF-8/LF PDB text with 80-column atom records.

- [ ] **Step 1: Implement preview from readiness and actual omissions**

`preview_pdb_export()` must:

- fail closed for readiness states other than `Ready` and `ReadyWithRenumbering`;
- turn `serial.renumber` into a stable informational/loss entry;
- detect only real source semantics that the normalized slice omits;
- sort and deduplicate entries by ordinal `(code, message)`;
- report the actual output model count without serializing the destination.

Do not treat ordinary whitespace normalization, UUID/revision regeneration, or provenance IDs as scientific loss.

- [ ] **Step 2: Project exact model inputs once**

Resolve each Structure by exact `structure_id` to one hierarchy and optional unique occupancy, B-factor, and FrameSet. Use FrameSet coordinates as the output models when present; otherwise use the Structure coordinates once. Order independent Structures by source/revision creation evidence with UUID as the deterministic final tiebreaker; never use dictionary insertion order.

- [ ] **Step 3: Emit the minimum normalized record set**

For one output model, emit only `ATOM`/`HETATM` records followed by `END`. For multiple output models, wrap every model in:

```text
MODEL        1
...
ENDMDL
```

and end the file with `END`. Allocate model numbers `1..N` and atom serials deterministically. Preserve valid source atom serials only when readiness permits; otherwise allocate `1..atom_count` in Structure atom order.

Atom lines must follow the existing P1 budgets:

- columns 1–6 record kind, 7–11 serial, 13–16 deterministic atom-name alignment;
- column 17 altloc, 18–20 residue name, 22 chain ID, 23–26 residue number, 27 insertion code;
- columns 31–54 coordinates as `8.3` angstrom;
- columns 55–60 occupancy and 61–66 B-factor as `6.2`, blank for absent/partial `NaN`;
- columns 77–78 canonical element symbol derived from atomic number;
- columns 79–80 blank in this slice.

Reject newlines/control characters, non-finite values, invalid live arrays, or width overflow at the writer trust boundary even after preview. Normalize negative zero before formatting. Use locale-independent Python numeric formatting and one LF per record.

- [ ] **Step 4: Publish atomically**

Use the existing `atomic_write_chunks`; call the cancellation callback before expensive validation and during chunk emission. Cancellation or any writer error must leave no destination or sibling temporary file. Do not introduce another writer class, configuration object, or temporary-path helper.

- [ ] **Step 5: Expose and verify GREEN**

Add `preview_pdb_export` and `export_pdb` to `ChemBlender.core.exporters.__all__` and update the architecture inventory for the new source file.

```powershell
& $pythonBin -m unittest tests.test_pdb_export_readiness tests.test_pdb_exporter -v
```

- [ ] **Step 6: Commit the core writer**

```powershell
git add -- .agents/active/2.4.0-pdb-export.md .agents/reference/code-architecture-guide.md ChemBlender/core/exporters/pdb.py ChemBlender/core/exporters/__init__.py docs/quantum-visualization/2.4.0/pdb-export-contract.md tests/test_pdb_exporter.py tests/test_quantum_visualization_docs.py
git diff --cached --check
git commit -m "feat: add deterministic native PDB export"
```

---

### Task 3: Qualify model, hierarchy, loss, and cancellation boundaries

**Files:**
- Modify: `ChemBlender/core/exporters/pdb.py`
- Modify: `tests/test_pdb_exporter.py`

**Interfaces:**
- Consumes: Task 2 writer.
- Produces: executable evidence that normalized PDB output is deterministic and fail closed.

- [ ] **Step 1: Add focused failing tests**

Cover:

1. reversed tuple/dict insertion order produces identical bytes;
2. `ATOM` and `HETATM`, blank/nonblank chain, altloc and insertion code retain their fields;
3. invalid or duplicate source serials renumber predictably;
4. complete and partial occupancy/B-factor format correctly, while wrong unit/shape/status fails;
5. a FrameSet emits one `MODEL` block per frame with stable numbering and no duplicate base frame;
6. independent Structures produce deterministic model ordering;
7. coordinate, serial, residue, model, name and element overflow fails before publication;
8. cancellation before validation and mid-write raises `ExportCancelled` without residue;
9. omitted topology/`CONECT`, cell/`CRYST1`, source-only records and formal charge each have stable loss codes;
10. `No CONECT` is enforced even when a topology is present.

- [ ] **Step 2: Run RED, implement only missing boundaries, rerun GREEN**

```powershell
& $pythonBin -m unittest tests.test_pdb_exporter -v
```

Expected RED must name a real missing boundary. Make the smallest shared writer correction; do not add PQR or general-purpose fixed-column abstractions.

- [ ] **Step 3: Commit the boundary proof**

```powershell
git add -- ChemBlender/core/exporters/pdb.py tests/test_pdb_exporter.py
git diff --cached --check
git commit -m "test: qualify native PDB export boundaries"
```

---

### Task 4: Prove Semantic native re-import and publish core capability

**Files:**
- Modify: `tests/test_pdb_exporter.py`
- Modify: `ChemBlender/core/reader_catalog.py`
- Modify: `tests/test_generated_docs_fresh.py`
- Modify: `docs/quantum-visualization/2.3.0/format-maturity-matrix.md`
- Regenerate: `docs/quantum-visualization/reader-capability-matrix.json`
- Regenerate: `docs/user/format-capabilities.json`
- Regenerate: `docs/user/formats.md`

**Interfaces:**
- Consumes: verified core writer and native `parse_pdb()`.
- Produces: PDB export capability `F5 / core / preview_confirmation`.

- [ ] **Step 1: Add Semantic native re-import tests**

Export to a temporary `.pdb`, parse it through native `parse_pdb()`, and compare only representable semantics:

- atomic numbers, coordinates, atom names and record kinds;
- model/frame count and frame coordinates;
- chain IDs, residue names/numbers, insertion codes and altlocs;
- occupancy and B-factor finite/blank masks and values within output precision.

Do not compare UUIDs, revisions, provenance IDs, raw lines, comments, topology, cell, formal charge, or original serial spelling; those are either regenerated or explicit losses.

- [ ] **Step 2: Add capability RED and minimal source change**

Require the generated PDB export object to equal:

```python
{
    "execution_mode": "core",
    "format_id": "pdb",
    "loss_policy": "preview_confirmation",
    "maturity": "F5",
}
```

Run the assertion and observe F0, then add only:

```python
"pdb": ("pdb", "F5", "core", "preview_confirmation"),
```

to `_READER_EXPORTS`.

- [ ] **Step 3: Regenerate and verify**

```powershell
& $pythonBin ChemBlender/scripts/generate_format_docs.py --write
& $pythonBin -m unittest tests.test_pdb_exporter tests.test_generated_docs_fresh -v
```

Only PDB export capability documentation may change. Dependency inventory must remain byte-identical. Do not add PDB to Project Browser format choices; this task is No UI.

- [ ] **Step 4: Commit capability publication**

```powershell
git add -- ChemBlender/core/reader_catalog.py docs/quantum-visualization/2.3.0/format-maturity-matrix.md docs/quantum-visualization/reader-capability-matrix.json docs/user/format-capabilities.json docs/user/formats.md tests/test_generated_docs_fresh.py tests/test_pdb_exporter.py
git diff --cached --check
git commit -m "docs: publish native PDB export capability"
```

---

### Task 5: Full qualification, reviews, and checkpoint

**Files:**
- Move: `.agents/active/2.4.0-pdb-export.md` to `.agents/completed/2.4.0-pdb-export.md`
- Modify: `tests/test_quantum_visualization_docs.py`
- Verify: every Task 1–4 file.

**Interfaces:**
- Consumes: all implementation commits.
- Produces: clean local PDB core-export checkpoint; no PDB UI or PQR work activated.

- [ ] **Step 1: Run focused and full Python verification**

```powershell
& $pythonBin -m unittest tests.test_pdb_export_readiness tests.test_pdb_exporter tests.test_pdb_reader tests.test_generated_docs_fresh tests.test_quantum_visualization_docs -v
& $pythonBin -m unittest discover -s tests -p "test_*.py" -v
& $pythonBin -m compileall -q ChemBlender worker tests
```

- [ ] **Step 2: Run package and real Blender verification**

Using Blender 5.1.2, run native extension validate/build, ZIP path/duplicate/CRC/wheel/hash audit, isolated install, repeated register/unregister/reload, and a core PDB export/re-import smoke. Prove the new writer import does not load optional stacks. A PDB UI smoke is outside this task.

- [ ] **Step 3: Run two independent reviews**

Perform specification-compliance and code-quality reviews against this plan. Fix every Critical, Important, and directly related Minor finding; rerun Steps 1–2 after fixes.

- [ ] **Step 4: Complete the cursor and checkpoint**

Record commits, RED/GREEN evidence, focused/full counts, deterministic bytes, loss confirmation, semantic native re-import, optional-import audit, Blender result, reviews, and `Remote CI: Not Run`. Move the cursor to completed and leave no active or queued PDB implementation.

```powershell
git diff --check
git status --short
git add -- .agents/completed/2.4.0-pdb-export.md tests/test_quantum_visualization_docs.py
git diff --cached --check
git commit -m "chore: checkpoint native PDB export"
git status --short
```

Stop. Do not begin PDB UI, PQR, Cube, Reader API stable, version, release, push, or PR work.
